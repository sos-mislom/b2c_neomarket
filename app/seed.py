from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import NAMESPACE_DNS, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import (
    Banner,
    CartItem,
    Category,
    Collection,
    CollectionProduct,
    FavoriteItem,
    NotificationSubscription,
    Order,
    OrderItem,
    OrderStatus,
    Product,
    ProductCharacteristic,
    ProductImage,
    ProductStatus,
    Sku,
    SkuImage,
    Store,
)


def stable_uuid(name: str) -> str:
    return str(uuid5(NAMESPACE_DNS, f"neomarket:{name}"))


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def seed_database(session: Session) -> None:
    has_products = session.scalar(select(Product.id).limit(1))
    if has_products:
        return

    settings = get_settings()
    now = utc_now()
    past = now - timedelta(days=45)

    store_specs = {
        "chainaya-polka": {
            "name": "Чайная Полка",
            "description": "Магазин листового чая на каждый день: зелёный, чёрный и подарочные боксы.",
            "rating": 4.9,
            "delivery_note": "Доставка за 1 день",
        },
        "east-merchant": {
            "name": "Восточный Лист",
            "description": "Китайский чай, улуны и пуэры с акцентом на свежие весенние поставки.",
            "rating": 4.8,
            "delivery_note": "Отправка в день заказа",
        },
        "leaf-and-cup": {
            "name": "Leaf & Cup",
            "description": "Матча, японский зелёный чай и редкие моносорта для домашнего ритуала.",
            "rating": 4.9,
            "delivery_note": "Бережная упаковка",
        },
        "tea-room-1910": {
            "name": "Tea Room 1910",
            "description": "Классический ассортимент: завтрачные чаи, бергамот и плотные улуновые позиции.",
            "rating": 4.7,
            "delivery_note": "Самовывоз и курьер",
        },
        "northern-herbs": {
            "name": "Северные Травы",
            "description": "Травяные и ягодные сборы, иван-чай и мягкие вечерние купажи.",
            "rating": 4.8,
            "delivery_note": "Без ароматизаторов",
        },
    }
    stores = {
        key: Store(
            id=stable_uuid(f"store:{key}"),
            slug=key,
            name=spec["name"],
            description=spec["description"],
            rating=spec["rating"],
            delivery_note=spec["delivery_note"],
            logo_url=f"/cdn/stores/{key}.svg",
            is_active=True,
            created_at=past,
            updated_at=now,
        )
        for key, spec in store_specs.items()
    }
    session.add_all(stores.values())

    category_specs = [
        ("tea", "Чай", "tea", "Основной каталог листового чая и матчи", None),
        ("green-tea", "Зелёный чай", "green-tea", "Сенча, лун цзин и другие лёгкие позиции", "tea"),
        ("black-tea", "Чёрный чай", "black-tea", "Завтрачные и ароматизированные бленды", "tea"),
        ("oolong", "Улун", "oolong", "Светлые и сливочные улуны", "tea"),
        ("puer", "Пуэр", "puer", "Выдержанные и плотные пуэры", "tea"),
        ("matcha", "Матча", "matcha", "Матча для чаши, венчика и латте", "tea"),
        ("herbal-blends", "Травяные сборы", "herbal-blends", "Ягодные, цветочные и мягкие вечерние смеси", None),
        ("ivan-tea", "Иван-чай", "ivan-tea", "Ферментированный иван-чай без добавок", "herbal-blends"),
        ("flower-fruit", "Цветочные и фруктовые", "flower-fruit", "Гибискус, ягоды, шиповник и цитрус", "herbal-blends"),
        ("gift-sets", "Наборы", "gift-sets", "Подарочные и дегустационные наборы", None),
        ("tea-boxes", "Подарочные боксы", "tea-boxes", "Готовые наборы для подарка", "gift-sets"),
        ("sampler-sets", "Дегустационные сеты", "sampler-sets", "Небольшие сеты для знакомства с ассортиментом", "gift-sets"),
    ]
    categories = {}
    for key, name, slug, description, parent_key in category_specs:
        categories[key] = Category(
            id=stable_uuid(f"category:{key}"),
            name=name,
            slug=slug,
            description=description,
            parent_id=stable_uuid(f"category:{parent_key}") if parent_key else None,
            seo_title=f"{name} | NeoMarket",
            seo_description=description,
            seo_keywords=["чай", slug, "neomarket"],
            meta_tags={"og_title": f"{name} | NeoMarket"},
            image_url=f"/cdn/categories/{slug}.jpg",
            is_active=True,
            created_at=past,
            updated_at=now,
        )
    session.add_all(categories.values())

    product_specs = [
        {
            "key": "sencha-yabukita-premium",
            "slug": "sencha-yabukita-premium",
            "title": "Сенча Yabukita Premium",
            "description": "Японская сенча первой весенней поставки. Чистый вкус, лёгкая сладость и ровный лист.",
            "store": "chainaya-polka",
            "category": "green-tea",
            "status": ProductStatus.MODERATED,
            "rating": 4.94,
            "popularity": 980,
            "discount_percent": 8,
            "product_characteristics": {
                "BRAND": "Shizuoka Leaf",
                "ORIGIN": "Япония, Сидзуока",
                "TEA_TYPE": "Сенча",
                "TASTE": "Свежая трава, морская сладость",
                "CAFFEINE": "Средний",
                "LEAF": "Листовой",
                "HARVEST": "Весна 2025",
            },
            "images": [
                "/cdn/products/sencha-yabukita-premium/main.jpg",
                "/cdn/products/sencha-yabukita-premium/detail.jpg",
            ],
            "skus": [
                {"key": "sencha-yabukita-premium-50g", "name": "50 г", "price_cents": 89000, "qty": 18},
                {"key": "sencha-yabukita-premium-100g", "name": "100 г", "price_cents": 159000, "qty": 11},
                {"key": "sencha-yabukita-premium-250g", "name": "250 г", "price_cents": 359000, "qty": 4},
            ],
        },
        {
            "key": "longjing-spring-reserve",
            "slug": "longjing-spring-reserve",
            "title": "Лун Цзин Spring Reserve",
            "description": "Классический колодезный дракон с ореховой сладостью и мягким долгим послевкусием.",
            "store": "east-merchant",
            "category": "green-tea",
            "status": ProductStatus.MODERATED,
            "rating": 4.88,
            "popularity": 760,
            "discount_percent": 10,
            "product_characteristics": {
                "BRAND": "West Lake Tea Farm",
                "ORIGIN": "Китай, Ханчжоу",
                "TEA_TYPE": "Лун Цзин",
                "TASTE": "Орехи, сладкий каштан",
                "CAFFEINE": "Средний",
                "LEAF": "Листовой",
                "HARVEST": "Весна 2025",
            },
            "images": ["/cdn/products/longjing-spring-reserve/main.jpg"],
            "skus": [
                {"key": "longjing-spring-reserve-50g", "name": "50 г", "price_cents": 109000, "qty": 14},
                {"key": "longjing-spring-reserve-100g", "name": "100 г", "price_cents": 199000, "qty": 6},
            ],
        },
        {
            "key": "gyokuro-asahi-shade",
            "slug": "gyokuro-asahi-shade",
            "title": "Гёкуро Asahi Shade",
            "description": "Теневой японский чай для спокойного вечернего заваривания. Плотный умами и мягкий аромат.",
            "store": "leaf-and-cup",
            "category": "green-tea",
            "status": ProductStatus.MODERATED,
            "rating": 4.91,
            "popularity": 620,
            "discount_percent": 5,
            "product_characteristics": {
                "BRAND": "Uji No Kaori",
                "ORIGIN": "Япония, Удзи",
                "TEA_TYPE": "Гёкуро",
                "TASTE": "Умами, сливочная зелень",
                "CAFFEINE": "Высокий",
                "LEAF": "Листовой",
                "HARVEST": "Весна 2025",
            },
            "images": ["/cdn/products/gyokuro-asahi-shade/main.jpg"],
            "skus": [
                {"key": "gyokuro-asahi-shade-50g", "name": "50 г", "price_cents": 179000, "qty": 9},
                {"key": "gyokuro-asahi-shade-100g", "name": "100 г", "price_cents": 339000, "qty": 4},
            ],
        },
        {
            "key": "assam-gold-breakfast",
            "slug": "assam-gold-breakfast",
            "title": "Assam Gold Breakfast",
            "description": "Насыщенный чёрный чай на каждый день. Хорошо держит молоко и плотный завтрак.",
            "store": "tea-room-1910",
            "category": "black-tea",
            "status": ProductStatus.MODERATED,
            "rating": 4.85,
            "popularity": 910,
            "discount_percent": 12,
            "product_characteristics": {
                "BRAND": "Halmari",
                "ORIGIN": "Индия, Ассам",
                "TEA_TYPE": "Ассам",
                "TASTE": "Солод, тёмный мёд",
                "CAFFEINE": "Высокий",
                "LEAF": "Листовой",
                "HARVEST": "Лето 2024",
            },
            "images": ["/cdn/products/assam-gold-breakfast/main.jpg"],
            "skus": [
                {"key": "assam-gold-breakfast-100g", "name": "100 г", "price_cents": 99000, "qty": 20},
                {"key": "assam-gold-breakfast-250g", "name": "250 г", "price_cents": 229000, "qty": 9},
            ],
        },
        {
            "key": "darjeeling-first-flush",
            "slug": "darjeeling-first-flush",
            "title": "Darjeeling First Flush",
            "description": "Лёгкий весенний дарджилинг с цветочным ароматом и сухим, чистым финишем.",
            "store": "leaf-and-cup",
            "category": "black-tea",
            "status": ProductStatus.MODERATED,
            "rating": 4.82,
            "popularity": 540,
            "discount_percent": 6,
            "product_characteristics": {
                "BRAND": "Makaibari",
                "ORIGIN": "Индия, Дарджилинг",
                "TEA_TYPE": "Дарджилинг",
                "TASTE": "Цветы, виноградная кожура",
                "CAFFEINE": "Средний",
                "LEAF": "Листовой",
                "HARVEST": "Весна 2025",
            },
            "images": ["/cdn/products/darjeeling-first-flush/main.jpg"],
            "skus": [
                {"key": "darjeeling-first-flush-50g", "name": "50 г", "price_cents": 149000, "qty": 12},
                {"key": "darjeeling-first-flush-100g", "name": "100 г", "price_cents": 279000, "qty": 7},
            ],
        },
        {
            "key": "earl-grey-bergamot",
            "slug": "earl-grey-bergamot",
            "title": "Earl Grey Bergamot",
            "description": "Спокойный чёрный чай с натуральным бергамотом. Подходит для большой кружки и офиса.",
            "store": "chainaya-polka",
            "category": "black-tea",
            "status": ProductStatus.MODERATED,
            "rating": 4.78,
            "popularity": 690,
            "discount_percent": 14,
            "product_characteristics": {
                "BRAND": "House Blend",
                "ORIGIN": "Шри-Ланка / Италия",
                "TEA_TYPE": "Эрл Грей",
                "TASTE": "Бергамот, цитрус",
                "CAFFEINE": "Средний",
                "LEAF": "Листовой",
                "HARVEST": "Купаж 2025",
            },
            "images": ["/cdn/products/earl-grey-bergamot/main.jpg"],
            "skus": [
                {"key": "earl-grey-bergamot-100g", "name": "100 г", "price_cents": 89000, "qty": 17},
                {"key": "earl-grey-bergamot-250g", "name": "250 г", "price_cents": 199000, "qty": 8},
            ],
        },
        {
            "key": "tieguanyin-classic",
            "slug": "tieguanyin-classic",
            "title": "Те Гуань Инь Classic",
            "description": "Светлый улун с чистой орхидеей, сливочной текстурой и мягкой сладостью.",
            "store": "east-merchant",
            "category": "oolong",
            "status": ProductStatus.MODERATED,
            "rating": 4.89,
            "popularity": 700,
            "discount_percent": 7,
            "product_characteristics": {
                "BRAND": "Anxi Tea Co.",
                "ORIGIN": "Китай, Аньси",
                "TEA_TYPE": "Те Гуань Инь",
                "TASTE": "Орхидея, сливки",
                "CAFFEINE": "Средний",
                "LEAF": "Листовой",
                "HARVEST": "Весна 2025",
            },
            "images": ["/cdn/products/tieguanyin-classic/main.jpg"],
            "skus": [
                {"key": "tieguanyin-classic-50g", "name": "50 г", "price_cents": 119000, "qty": 15},
                {"key": "tieguanyin-classic-100g", "name": "100 г", "price_cents": 219000, "qty": 7},
            ],
        },
        {
            "key": "milk-oolong-creamy",
            "slug": "milk-oolong-creamy",
            "title": "Milk Oolong Creamy",
            "description": "Плотный ароматизированный улун со сливочной подачей и мягким десертным профилем.",
            "store": "tea-room-1910",
            "category": "oolong",
            "status": ProductStatus.MODERATED,
            "rating": 4.76,
            "popularity": 810,
            "discount_percent": 15,
            "product_characteristics": {
                "BRAND": "Fujian Milky Leaf",
                "ORIGIN": "Китай, Фуцзянь",
                "TEA_TYPE": "Молочный улун",
                "TASTE": "Сливки, печенье",
                "CAFFEINE": "Средний",
                "LEAF": "Листовой",
                "HARVEST": "Осень 2024",
            },
            "images": ["/cdn/products/milk-oolong-creamy/main.jpg"],
            "skus": [
                {"key": "milk-oolong-creamy-100g", "name": "100 г", "price_cents": 129000, "qty": 13},
                {"key": "milk-oolong-creamy-250g", "name": "250 г", "price_cents": 299000, "qty": 5},
            ],
        },
        {
            "key": "shu-puer-gongting-2018",
            "slug": "shu-puer-gongting-2018",
            "title": "Шу Пуэр Gongting 2018",
            "description": "Плотный, тёмный пуэр с древесной сладостью и спокойным шоколадным послевкусием.",
            "store": "east-merchant",
            "category": "puer",
            "status": ProductStatus.MODERATED,
            "rating": 4.83,
            "popularity": 470,
            "discount_percent": 9,
            "product_characteristics": {
                "BRAND": "Menghai Craft",
                "ORIGIN": "Китай, Юньнань",
                "TEA_TYPE": "Шу пуэр",
                "TASTE": "Какао, древесина",
                "CAFFEINE": "Средний",
                "LEAF": "Листовой",
                "HARVEST": "Выдержка с 2018",
            },
            "images": ["/cdn/products/shu-puer-gongting-2018/main.jpg"],
            "skus": [
                {"key": "shu-puer-gongting-2018-100g", "name": "100 г", "price_cents": 139000, "qty": 10},
                {"key": "shu-puer-gongting-2018-357g", "name": "357 г блин", "price_cents": 459000, "qty": 3},
            ],
        },
        {
            "key": "matcha-ceremonial-aoki",
            "slug": "matcha-ceremonial-aoki",
            "title": "Matcha Ceremonial Aoki",
            "description": "Яркая церемониальная матча для чаши. Хорошо взбивается, даёт густую пену и сладкий финиш.",
            "store": "leaf-and-cup",
            "category": "matcha",
            "status": ProductStatus.MODERATED,
            "rating": 4.96,
            "popularity": 940,
            "discount_percent": 4,
            "product_characteristics": {
                "BRAND": "Aoki Matcha Works",
                "ORIGIN": "Япония, Киото",
                "TEA_TYPE": "Матча",
                "TASTE": "Умами, белый шоколад",
                "CAFFEINE": "Высокий",
                "LEAF": "Порошок",
                "HARVEST": "Весна 2025",
            },
            "images": ["/cdn/products/matcha-ceremonial-aoki/main.jpg"],
            "skus": [
                {"key": "matcha-ceremonial-aoki-30g", "name": "30 г", "price_cents": 169000, "qty": 12},
                {"key": "matcha-ceremonial-aoki-100g", "name": "100 г", "price_cents": 459000, "qty": 5},
            ],
        },
        {
            "key": "ivan-chai-taiga",
            "slug": "ivan-chai-taiga",
            "title": "Иван-чай Таёжный",
            "description": "Ферментированный иван-чай без ароматизаторов. Мягкий, хлебный, для долгого чаепития.",
            "store": "northern-herbs",
            "category": "ivan-tea",
            "status": ProductStatus.MODERATED,
            "rating": 4.74,
            "popularity": 660,
            "discount_percent": 11,
            "product_characteristics": {
                "BRAND": "Taezhny Fermer",
                "ORIGIN": "Россия, Карелия",
                "TEA_TYPE": "Иван-чай",
                "TASTE": "Хлебная корочка, сухофрукты",
                "CAFFEINE": "Без кофеина",
                "LEAF": "Листовой",
                "HARVEST": "Лето 2025",
            },
            "images": ["/cdn/products/ivan-chai-taiga/main.jpg"],
            "skus": [
                {"key": "ivan-chai-taiga-100g", "name": "100 г", "price_cents": 69000, "qty": 24},
                {"key": "ivan-chai-taiga-250g", "name": "250 г", "price_cents": 149000, "qty": 10},
            ],
        },
        {
            "key": "hibiscus-rosehip-bright",
            "slug": "hibiscus-rosehip-bright",
            "title": "Гибискус и Шиповник Bright",
            "description": "Кисло-сладкий ягодный сбор для большого чайника. Хорошо раскрывается и горячим, и холодным.",
            "store": "northern-herbs",
            "category": "flower-fruit",
            "status": ProductStatus.MODERATED,
            "rating": 4.69,
            "popularity": 520,
            "discount_percent": 13,
            "product_characteristics": {
                "BRAND": "Berry Bloom",
                "ORIGIN": "Россия",
                "TEA_TYPE": "Травяной сбор",
                "TASTE": "Клюква, шиповник",
                "CAFFEINE": "Без кофеина",
                "LEAF": "Купаж",
                "HARVEST": "Осень 2025",
            },
            "images": ["/cdn/products/hibiscus-rosehip-bright/main.jpg"],
            "skus": [
                {"key": "hibiscus-rosehip-bright-100g", "name": "100 г", "price_cents": 79000, "qty": 16},
                {"key": "hibiscus-rosehip-bright-250g", "name": "250 г", "price_cents": 169000, "qty": 6},
            ],
        },
        {
            "key": "tea-box-evening-ritual",
            "slug": "tea-box-evening-ritual",
            "title": "Подарочный бокс Evening Ritual",
            "description": "Подарочный набор из зелёного чая, матчи и травяного купажа. Собран для спокойного вечернего ритуала.",
            "store": "chainaya-polka",
            "category": "tea-boxes",
            "status": ProductStatus.MODERATED,
            "rating": 4.84,
            "popularity": 430,
            "discount_percent": 9,
            "product_characteristics": {
                "BRAND": "NeoMarket Select",
                "ORIGIN": "Сборный набор",
                "TEA_TYPE": "Подарочный набор",
                "TASTE": "Зелёный чай, матча, травы",
                "CAFFEINE": "Смешанный",
                "FORMAT": "Подарочный бокс",
            },
            "images": ["/cdn/products/tea-box-evening-ritual/main.jpg"],
            "skus": [
                {"key": "tea-box-evening-ritual-12", "name": "12 позиций", "price_cents": 189000, "qty": 8},
            ],
        },
        {
            "key": "tea-sampler-weekend-market",
            "slug": "tea-sampler-weekend-market",
            "title": "Дегустационный сет Weekend Market",
            "description": "Небольшой сет из шести популярных вкусов для первого знакомства с каталогом.",
            "store": "tea-room-1910",
            "category": "sampler-sets",
            "status": ProductStatus.BLOCKED,
            "rating": 4.21,
            "popularity": 250,
            "discount_percent": 18,
            "product_characteristics": {
                "BRAND": "Tea Flight Co.",
                "ORIGIN": "Сборный набор",
                "TEA_TYPE": "Дегустационный набор",
                "TASTE": "Ассорти",
                "CAFFEINE": "Смешанный",
                "FORMAT": "Сэмплер",
            },
            "images": ["/cdn/products/tea-sampler-weekend-market/main.jpg"],
            "skus": [
                {"key": "tea-sampler-weekend-market-6x25", "name": "6 x 25 г", "price_cents": 149000, "qty": 3},
            ],
        },
    ]

    products: list[Product] = []
    for index, spec in enumerate(product_specs):
        created_at = now - timedelta(days=120 - index * 4)
        product = Product(
            id=stable_uuid(f"product:{spec['key']}"),
            slug=spec["slug"],
            title=spec["title"],
            description=spec["description"],
            status=spec["status"],
            store_id=stores[spec["store"]].id,
            category_id=categories[spec["category"]].id,
            is_deleted=False,
            is_blocked=spec["status"] == ProductStatus.BLOCKED,
            rating=spec["rating"],
            popularity=spec["popularity"],
            discount_percent=spec["discount_percent"],
            created_at=created_at,
            updated_at=now,
        )
        for ordering, image_url in enumerate(spec["images"]):
            product.images.append(ProductImage(url=image_url, ordering=ordering))
        for name, value in spec["product_characteristics"].items():
            product.characteristics.append(ProductCharacteristic(name=name, value=value))
        for ordering, sku_spec in enumerate(spec["skus"]):
            sku = Sku(
                id=stable_uuid(f"sku:{sku_spec['key']}"),
                name=sku_spec["name"],
                price_cents=sku_spec["price_cents"],
                active_quantity=sku_spec["qty"],
                is_active=True,
                created_at=created_at + timedelta(minutes=ordering),
                updated_at=now,
            )
            sku.images.append(SkuImage(url=f"/cdn/skus/{sku_spec['key']}.jpg", ordering=0))
            product.skus.append(sku)
        products.append(product)

    session.add_all(products)

    collections = [
        Collection(
            id=stable_uuid("collection:green-harvest"),
            title="Зелёный чай новой поставки",
            description="Свежая весенняя подборка: сенча, лун цзин, гёкуро и матча.",
            cover_image_url="/cdn/collections/green-harvest.jpg",
            target_url="/collections/green-harvest",
            priority=10,
            start_date=date.today() - timedelta(days=7),
            is_active=True,
        ),
        Collection(
            id=stable_uuid("collection:breakfast-black-tea"),
            title="Чёрный чай на каждый день",
            description="Плотные и понятные позиции для большой кружки, офиса и завтрака.",
            cover_image_url="/cdn/collections/breakfast-black-tea.jpg",
            target_url="/collections/breakfast-black-tea",
            priority=20,
            start_date=date.today() - timedelta(days=5),
            is_active=True,
        ),
        Collection(
            id=stable_uuid("collection:gift-boxes"),
            title="Подарки и дегустационные наборы",
            description="Наборы для подарка и первого знакомства с чайной витриной.",
            cover_image_url="/cdn/collections/gift-boxes.jpg",
            target_url="/collections/gift-boxes",
            priority=30,
            start_date=date.today() - timedelta(days=2),
            is_active=True,
        ),
    ]
    session.add_all(collections)

    collection_links = [
        ("collection:green-harvest", "sencha-yabukita-premium", 1),
        ("collection:green-harvest", "longjing-spring-reserve", 2),
        ("collection:green-harvest", "gyokuro-asahi-shade", 3),
        ("collection:green-harvest", "matcha-ceremonial-aoki", 4),
        ("collection:breakfast-black-tea", "assam-gold-breakfast", 1),
        ("collection:breakfast-black-tea", "darjeeling-first-flush", 2),
        ("collection:breakfast-black-tea", "earl-grey-bergamot", 3),
        ("collection:gift-boxes", "tea-box-evening-ritual", 1),
        ("collection:gift-boxes", "milk-oolong-creamy", 2),
        ("collection:gift-boxes", "tea-sampler-weekend-market", 3),
    ]
    for collection_key, product_key, ordering in collection_links:
        session.add(
            CollectionProduct(
                collection_id=stable_uuid(collection_key),
                product_id=stable_uuid(f"product:{product_key}"),
                ordering=ordering,
            )
        )

    banners = [
        Banner(
            id=stable_uuid("banner:green-harvest"),
            title="Зелёный чай весенней поставки",
            image_url="/cdn/banners/green-harvest.jpg",
            link="/collections/green-harvest",
            priority=10,
            placement="home",
            is_active=True,
            start_at=now - timedelta(days=3),
            end_at=now + timedelta(days=30),
        ),
        Banner(
            id=stable_uuid("banner:black-tea"),
            title="Чёрный чай на каждый день",
            image_url="/cdn/banners/black-tea.jpg",
            link="/collections/breakfast-black-tea",
            priority=20,
            placement="home",
            is_active=True,
            start_at=now - timedelta(days=2),
            end_at=now + timedelta(days=21),
        ),
        Banner(
            id=stable_uuid("banner:gift-boxes"),
            title="Подарочные боксы к выходным",
            image_url="/cdn/banners/gift-boxes.jpg",
            link="/collections/gift-boxes",
            priority=30,
            placement="home",
            is_active=True,
            start_at=now - timedelta(days=1),
            end_at=now + timedelta(days=14),
        ),
    ]
    session.add_all(banners)

    favorite_products = ["sencha-yabukita-premium", "matcha-ceremonial-aoki", "tea-sampler-weekend-market"]
    for index, product_key in enumerate(favorite_products):
        session.add(
            FavoriteItem(
                id=stable_uuid(f"favorite:{settings.demo_user_id}:{product_key}"),
                user_id=settings.demo_user_id,
                product_id=stable_uuid(f"product:{product_key}"),
                added_at=now - timedelta(days=index + 1),
            )
        )

    session.add(
        NotificationSubscription(
            id=stable_uuid(f"subscription:{settings.demo_user_id}:gyokuro-asahi-shade"),
            user_id=settings.demo_user_id,
            product_id=stable_uuid("product:gyokuro-asahi-shade"),
            notify_on=["PRICE_DOWN", "IN_STOCK"],
            created_at=now - timedelta(days=2),
        )
    )

    session.add_all(
        [
            CartItem(
                id=stable_uuid("cart-item:demo:sencha"),
                user_id=settings.demo_user_id,
                session_id=None,
                sku_id=stable_uuid("sku:sencha-yabukita-premium-100g"),
                quantity=1,
                created_at=now - timedelta(hours=4),
                updated_at=now - timedelta(hours=1),
            ),
            CartItem(
                id=stable_uuid("cart-item:demo:matcha"),
                user_id=settings.demo_user_id,
                session_id=None,
                sku_id=stable_uuid("sku:matcha-ceremonial-aoki-30g"),
                quantity=1,
                created_at=now - timedelta(hours=3),
                updated_at=now - timedelta(hours=1),
            ),
            CartItem(
                id=stable_uuid("cart-item:demo:sampler"),
                user_id=settings.demo_user_id,
                session_id=None,
                sku_id=stable_uuid("sku:tea-sampler-weekend-market-6x25"),
                quantity=1,
                created_at=now - timedelta(hours=2),
                updated_at=now - timedelta(hours=1),
            ),
            CartItem(
                id=stable_uuid("cart-item:guest:assam"),
                user_id=None,
                session_id=settings.demo_session_id,
                sku_id=stable_uuid("sku:assam-gold-breakfast-100g"),
                quantity=1,
                created_at=now - timedelta(hours=1),
                updated_at=now - timedelta(minutes=30),
            ),
        ]
    )

    orders = [
        {
            "key": "order:7001",
            "number": 7001,
            "user_id": settings.demo_user_id,
            "status": OrderStatus.PAID,
            "created_at": now - timedelta(days=8),
            "items": [
                ("assam-gold-breakfast", "assam-gold-breakfast-100g", 1),
                ("ivan-chai-taiga", "ivan-chai-taiga-100g", 2),
            ],
        },
        {
            "key": "order:7002",
            "number": 7002,
            "user_id": settings.demo_user_id,
            "status": OrderStatus.DELIVERED,
            "created_at": now - timedelta(days=19),
            "items": [
                ("matcha-ceremonial-aoki", "matcha-ceremonial-aoki-30g", 1),
            ],
        },
        {
            "key": "order:7101",
            "number": 7101,
            "user_id": "22222222-2222-2222-2222-222222222222",
            "status": OrderStatus.DELIVERED,
            "created_at": now - timedelta(days=12),
            "items": [
                ("sencha-yabukita-premium", "sencha-yabukita-premium-100g", 1),
                ("earl-grey-bergamot", "earl-grey-bergamot-100g", 1),
            ],
        },
        {
            "key": "order:7102",
            "number": 7102,
            "user_id": "33333333-3333-3333-3333-333333333333",
            "status": OrderStatus.DELIVERED,
            "created_at": now - timedelta(days=16),
            "items": [
                ("tieguanyin-classic", "tieguanyin-classic-100g", 1),
                ("milk-oolong-creamy", "milk-oolong-creamy-100g", 1),
            ],
        },
        {
            "key": "order:7103",
            "number": 7103,
            "user_id": "44444444-4444-4444-4444-444444444444",
            "status": OrderStatus.DELIVERED,
            "created_at": now - timedelta(days=6),
            "items": [
                ("assam-gold-breakfast", "assam-gold-breakfast-250g", 1),
                ("tea-box-evening-ritual", "tea-box-evening-ritual-12", 1),
            ],
        },
    ]

    sku_price_map = {}
    product_title_map = {}
    sku_name_map = {}
    for spec in product_specs:
        product_id = stable_uuid(f"product:{spec['key']}")
        product_title_map[product_id] = spec["title"]
        for sku_spec in spec["skus"]:
            sku_id = stable_uuid(f"sku:{sku_spec['key']}")
            sku_price_map[sku_id] = sku_spec["price_cents"]
            sku_name_map[sku_id] = sku_spec["name"]

    for order_spec in orders:
        total_amount = 0
        order = Order(
            id=stable_uuid(order_spec["key"]),
            order_number=order_spec["number"],
            user_id=order_spec["user_id"],
            status=order_spec["status"],
            total_amount=0,
            currency="RUB",
            reservation_released=order_spec["status"] == OrderStatus.CANCELLED,
            created_at=order_spec["created_at"],
            updated_at=order_spec["created_at"] + timedelta(hours=2),
            cancelled_at=None,
        )
        for product_key, sku_key, quantity in order_spec["items"]:
            product_id = stable_uuid(f"product:{product_key}")
            sku_id = stable_uuid(f"sku:{sku_key}")
            unit_price = sku_price_map[sku_id]
            line_total = unit_price * quantity
            total_amount += line_total
            order.items.append(
                OrderItem(
                    id=stable_uuid(f"order-item:{order_spec['key']}:{sku_key}"),
                    product_id=product_id,
                    sku_id=sku_id,
                    product_title=product_title_map[product_id],
                    sku_name=sku_name_map[sku_id],
                    unit_price=unit_price,
                    quantity=quantity,
                    line_total=line_total,
                )
            )
        order.total_amount = total_amount
        session.add(order)

    session.commit()
