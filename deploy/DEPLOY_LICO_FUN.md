# Deploy EcoPlay to `lico.fun`

This setup serves:

- operator pages: `https://lico.fun/`
- public QR pages: `https://lico.fun/user`
- backend API: `https://lico.fun/api/...`

## 1. Copy the project to the server

```bash
scp -r /Users/zhouyuyan/Documents/eco_play_workspace root@120.25.194.179:/opt/eco_play_workspace
```

Or clone the GitHub repository directly on the server:

```bash
cd /opt
git clone git@github.com:JokerOldroger/eco_play_workspace.git
mv eco_play_workspace /opt/eco_play_workspace
```

## 2. Install backend dependencies

```bash
cd /opt/eco_play_workspace
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
```

If smart chat should use OpenAI, create:

```bash
cp backend/.env.example backend/.env
```

Then edit `backend/.env`:

```bash
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_CHAT_MODEL=gpt-5-mini
```

## 3. Build the frontend

```bash
cd "/opt/eco_play_workspace/frontend/EcoPlay Campus Energy App"
npm install
npm run build
mkdir -p /var/www/eco_play_workspace/frontend-dist
cp -R dist/* /var/www/eco_play_workspace/frontend-dist/
```

## 4. Install the backend as a service

```bash
cp /opt/eco_play_workspace/deploy/ecoplay-backend.service /etc/systemd/system/ecoplay-backend.service
systemctl daemon-reload
systemctl enable ecoplay-backend
systemctl restart ecoplay-backend
systemctl status ecoplay-backend
```

The backend listens on:

```text
http://127.0.0.1:5001
```

## 5. Configure Nginx

```bash
cp /opt/eco_play_workspace/deploy/nginx-lico-fun.conf /etc/nginx/conf.d/ecoplay.conf
nginx -t
systemctl reload nginx
```

## 6. Recommended HTTPS

If `lico.fun` points to `120.25.194.179`, install HTTPS with Certbot:

```bash
certbot --nginx -d lico.fun -d www.lico.fun
```

After HTTPS is active, users should scan QR codes that point to `https://lico.fun/...`, not the raw IP address.

## 7. Public QR entry URLs

General public page:

```text
https://lico.fun/user
```

First real test room:

```text
https://lico.fun/user?building=Sustainability%20Office&room=Sustainability%20Office
```

Stats page:

```text
https://lico.fun/user/stats?building=Sustainability%20Office
```

Chat page:

```text
https://lico.fun/user/chat?building=Sustainability%20Office&room=Sustainability%20Office
```

## 8. Operator pages

Operator pages stay on the main routes:

```text
https://lico.fun/
https://lico.fun/stats
https://lico.fun/chat
https://lico.fun/settings
```

If this will be used publicly, protect the operator routes with login or restrict them by network before production launch.
