[Unit]
Description=MogBot Flask backend (gunicorn)
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/mogbot
EnvironmentFile=/opt/mogbot/.env
ExecStart=/opt/mogbot/.venv/bin/gunicorn -w 2 -b 0.0.0.0:__BACKEND_PORT__ --timeout 120 backend.wsgi:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
