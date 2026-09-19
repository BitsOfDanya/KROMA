# Frontend

Существующий дизайн KROMA: Next.js / React / TypeScript, MapLibre, Zustand, TanStack Query.

Из корня: `npm ci --prefix frontend`, затем `npm run dev --prefix frontend`. Backend по умолчанию http://127.0.0.1:8000; `KROMA_BACKEND_URL` меняет proxy при запуске/сборке. `NEXT_PUBLIC_API_BASE_URL` задаёт прямой origin API вместо proxy, если это нужно deployment.

Страницы: Overview `/`, Events `/events`, Analytics `/analytics`, Analysis `/analytics?tab=area`, Data `/explorer`, Predict `/predict`, About `/about`, Research `/research`. Operator menu содержит сведения о команде.

SCENARIO явно помечает синтетическую динамику. TRAIN prediction показывает in-sample предупреждение. TEST не наносится на карту. Predict принимает существующий полный TRAIN package; JPEG не выдаётся за вход модели.

Проверки: `npm run typecheck`, `npm run lint`, `npm test`, `npm run build` из `frontend`. Полная инструкция и demo — в корневом [README](../README.md).
