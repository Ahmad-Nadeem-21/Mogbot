# MogBot on AWS (Terraform)

Provisions everything needed to run MogBot on AWS:

- **Backend**: one Lightsail instance (Ubuntu, gunicorn + systemd), fronted
  by a CloudFront distribution that exists solely to get free HTTPS
  (`*.cloudfront.net`) without a custom domain or certbot.
- **Frontend**: `web/` served from a private S3 bucket through its own
  CloudFront distribution (Origin Access Control - the bucket itself has no
  public access).

This is **not required** to deploy MogBot to AWS - for a single box you
could click through the console just as easily. This exists so the setup
is reproducible and destroyable with one command instead of a one-off
console session you'd have to remember and repeat by hand.

**Nothing here has been applied against a real AWS account.** Review the
plan (`terraform plan`) before you `apply` - it creates real, billed
resources under your AWS account.

## Cost

Roughly **$5-12/month** in AWS infrastructure at this app's scale (Lightsail
`micro_3_0` ≈ $5/mo, S3 + CloudFront a few cents to ~$2/mo, likely $0 during
your first 12 months on the AWS Free Tier). The Anthropic API bill is
separate, billed by Anthropic directly at Claude Sonnet 5 rates, and scales
with usage - roughly $0.08-0.10 per completed interview session. Milestone
8's rate limits (10 sessions/hr, 60 answers/hr) bound the worst case.

## Prerequisites

- An AWS account, with the AWS CLI installed and configured (`aws configure`
  or an equivalent credential source) for a user/role that can create
  Lightsail, S3, CloudFront, and IAM-policy resources.
- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.5.
- `bash`, `rsync`, `ssh`, and the `aws` CLI on your PATH for the deploy
  scripts. On Windows, run them from Git Bash or WSL - not PowerShell.
- Your Anthropic API key on hand (you'll be prompted for it during
  `deploy_backend.sh` - it's written straight to `.env` on the instance and
  never touches Terraform state or this repo).

## Deploy

```bash
cd terraform
terraform init
terraform plan      # review what will be created
terraform apply      # creates real, billed AWS resources

./scripts/deploy_backend.sh    # rsyncs the app, installs deps, prompts for
                                # ANTHROPIC_API_KEY, starts the systemd service
./scripts/deploy_frontend.sh   # points web/ at the deployed API, syncs to S3,
                                # invalidates the CloudFront cache
```

Then open the `frontend_url` Terraform output in a browser.

## Updating after a code change

Re-run whichever deploy script matches what changed - both are idempotent:

```bash
./scripts/deploy_backend.sh    # backend/agents/core changes
./scripts/deploy_frontend.sh   # web/ changes
```

`deploy_backend.sh` won't overwrite an existing `.env` on the instance, so
your API key survives repeated deploys. To rotate the key, SSH in
(`ssh -i <saved-key> ubuntu@$(terraform output -raw backend_static_ip)`) and
edit `/opt/mogbot/.env` directly, then `sudo systemctl restart mogbot`.

## Security notes

- **`terraform.tfstate` contains the generated SSH private key in
  plaintext** (Terraform state always contains every attribute of every
  resource it manages, sensitive or not). Do not commit it - it's already
  covered by `.gitignore` - and consider a remote state backend with
  encryption at rest (S3 + a KMS-encrypted bucket) if this ever stops being
  a single-person experiment.
- SSH (port 22) defaults to open (`0.0.0.0/0`) so this works out of the box.
  Narrow `ssh_allowed_cidrs` in `variables.tf` to your own IP once you know
  it (check `https://checkip.amazonaws.com`).
- The backend port is firewalled to CloudFront's IP range only
  (`cidr_list_aliases = ["cloudfront"]` in `lightsail.tf`) - the origin
  can't be reached directly, bypassing HTTPS or rate limiting.
- `flask-limiter`'s in-memory storage is per-process, which is fine for
  this single-instance setup. If you ever scale to multiple backend
  instances, rate limits need a shared store (e.g. Redis / ElastiCache) or
  each instance enforces its own limit independently.
- The ANTHROPIC_API_KEY lives only in `/opt/mogbot/.env` on the instance -
  it is never in `user_data`, never in a Lightsail-visible attribute, and
  never in Terraform state.

## Teardown

```bash
cd terraform
terraform destroy
```

This deletes the Lightsail instance (and its local disk - the SQLite
session DB and vector-memory JSON on it, so back those up first if you care
about the data), the static IP, both CloudFront distributions, and the S3
bucket (only if empty - `deploy_frontend.sh`'s `--delete` sync means it
usually is; if not, empty it first with `aws s3 rm s3://<bucket> --recursive`).

## Known limitations / things to harden later

- Single Lightsail instance: no auto-scaling, no zero-downtime redeploys,
  and both the SQLite session DB and the vector-memory JSON file live on
  its local disk - losing the instance loses that data (see
  ACTION_PLAN.md Milestone 9's persistent-volume note if you outgrow this).
- No custom domain / ACM certificate - both CloudFront distributions use
  the shared `*.cloudfront.net` certificate. Add an `aws_acm_certificate`
  (in `us-east-1`, required for CloudFront) and an `aws_route53_record` if
  you want a real domain.
- No CI/CD - the deploy scripts are meant to be run by hand.
