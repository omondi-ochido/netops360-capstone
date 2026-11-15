#!/usr/bin/env bash
set -e

echo "=== 1. Setting up Backend Virtual Environment ==="
python3 -m venv backend/.venv
backend/.venv/bin/pip install --upgrade pip

if [ -s backend/requirements.txt ]; then
    backend/.venv/bin/pip install -r backend/requirements.txt
else
    backend/.venv/bin/pip install flask
    backend/.venv/bin/pip freeze > backend/requirements.txt
fi

echo "=== 2. Installing Frontend Dependencies ==="
cd frontend
if [ -s package.json ]; then
    npm install
else
    npm init -y
    npm install react react-dom
    npm install -D vite @vitejs/plugin-react
fi

echo "=== 3. Configuring Frontend .env ==="
if [ -f .env.example ]; then
    cp -n .env.example .env
else
    echo "VITE_API_BASE_URL=http://127.0.0" > .env
fi
cd ..

echo "=== Setup Complete! ==="
