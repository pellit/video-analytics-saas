## Tests End-to-End (E2E)

Usamos Playwright para pruebas E2E del frontend. Esto verifica la integración completa (frontend + backend).

1) Instalar dependencias (en la carpeta `frontend`):

```bash
cd frontend
npm install
npx playwright install
```

2) Tener el backend y frontend corriendo. Por ejemplo:
```bash
# Levantar el backend (desde el root del repo)
docker compose -f video-analytics-saas/docker-compose.yml up -d api db redis

# Levantar frontend localmente
cd frontend
npm run dev
```

3) Ejecutar los tests E2E (desde `frontend`):
```bash
npm run test:e2e
# O con UI
npm run test:e2e:headed
```

Nota: El test de ejemplo asume que existe un usuario `admin@video-saas.com` con contraseña `admin123` (como en `DatabaseSeeder`).

# Vue 3 + Vite

This template should help get you started developing with Vue 3 in Vite. The template uses Vue 3 `<script setup>` SFCs, check out the [script setup docs](https://v3.vuejs.org/api/sfc-script-setup.html#sfc-script-setup) to learn more.

Learn more about IDE Support for Vue in the [Vue Docs Scaling up Guide](https://vuejs.org/guide/scaling-up/tooling.html#ide-support).


## RUN TEST
export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh" && nvm use 20 && cd /home/pta/video-analytics-saas/video-analytics-saas/frontend && E2E_BASE_URL=https://dev.pellit.com.ar E2E_API_URL=https://dev.pellit.com.ar/api npx playwright test --reporter=list 2>&1