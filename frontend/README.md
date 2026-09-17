# Frontend

Next.js 16 (App Router) + TypeScript + MapLibre GL. Оперативная карта, инциденты, таймлайн с ретроспективой, аналитика, режимы LIVE/REPLAY. Обзор экранов и фич — в корневом [README](../README.md).

Локально:

```bash
npm install
npm run dev
```

Страница на `http://localhost:3000`. Backend по умолчанию ожидается на `http://localhost:8000` (переопределяется через `NEXT_PUBLIC_API_BASE_URL`).

Скрипты:

```bash
npm run typecheck   # tsc --noEmit
npm run lint        # eslint
npm run build       # production-сборка (next build)
npx vitest run      # unit-тесты (lib/*)
```

Структура — `src/app` (страницы), `src/features` (карта, инциденты, таймлайн, слои, аналитика — по фиче), `src/lib/api` (типизированный клиент + React Query хуки), `src/state` (Zustand: тема, режим, фильтры), `src/config/map.ts` (провайдеры тайлов, переопределяются через `NEXT_PUBLIC_MAP_*`).
