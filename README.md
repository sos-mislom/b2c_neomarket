# NeoMarket B2C

Production-like B2C витрина NeoMarket: Python/FastAPI backend, PostgreSQL, `nginx` web-tier и microfrontend shell.

Что внутри:
- каталог и карточка товара;
- дерево категорий, breadcrumbs, фильтры и facets;
- корзина и валидация корзины;
- избранное и подписки на товар;
- баннеры и подборки главной страницы;
- checkout, история заказов и отмена заказа;
- dynamic `/cdn/*` placeholders для mock asset path;
- shell + microfrontends `home`, `catalog`, `customer`;
- `docker-compose` стек: `web` + `api` + `postgres`.

## Источники контракта

- `https://github.com/tochka-public/NeoMarket---Student-Guide`
- `https://github.com/URFU2026-NeoMarket/neomarket-protocols`

## Быстрый старт

```bash
cp .env.example .env
docker compose up -d --build
```

API после запуска:
- storefront: `http://localhost:8080`
- API docs: `http://localhost:8080/docs`
- OpenAPI: `http://localhost:8080/openapi.json`

## Microfrontends

Shell грузит три независимых фронтовых модуля:
- `home` — баннеры, подборки и вход в категории;
- `catalog` — листинг, filters/facets и product detail;
- `customer` — cart, favorites, orders.

Все microfront-модули живут как отдельные web components с собственным shadow DOM и lazy-loading через shell.

## Demo данные

Сервис при первом старте сам создаёт схему и сидит БД.

Для тестов уже подготовлены:
- demo user: `11111111-1111-1111-1111-111111111111`
- demo guest session: `sess-demo-001`
- единая моковая база чая с несколькими магазинами: `Чайная Полка`, `Восточный Лист`, `Leaf & Cup`, `Tea Room 1910`, `Северные Травы`

Примеры:

```bash
curl http://localhost:8080/healthz

curl http://localhost:8080/api/v1/bootstrap

curl --globoff --get \
  --data-urlencode 'search=Yabukita' \
  --data-urlencode 'filters[store]=Чайная Полка' \
  'http://localhost:8080/api/v1/products'

curl 'http://localhost:8080/api/v1/categories/path/tea/green-tea?include_product_count=true'

curl -H 'X-User-Id: 11111111-1111-1111-1111-111111111111' \
  http://localhost:8080/api/v1/cart

curl -H 'X-User-Id: 11111111-1111-1111-1111-111111111111' \
  http://localhost:8080/api/v1/orders
```

## Основные ручки

- `GET /api/v1/products`
- `GET /api/v1/products/{id}`
- `GET /api/v1/products/{product_id}/skus`
- `GET /api/v1/categories`
- `GET /api/v1/categories/{id}`
- `GET /api/v1/categories/{id}/filters`
- `GET /api/v1/catalog/facets`
- `GET /api/v1/breadcrumbs`
- `GET /api/v1/cart`
- `POST /api/v1/cart/items`
- `GET /api/v1/favorites`
- `POST /api/v1/favorites/{product_id}`
- `GET /api/v1/home/banners`
- `GET /api/v1/main/collections`
- `GET /api/v1/bootstrap`
- `POST /api/v1/orders/checkout`
- `GET /api/v1/orders`
- `POST /api/v1/orders/{order_id}/cancel`

## Smoke

После старта можно прогнать:

```bash
./scripts/smoke_test.sh
```
