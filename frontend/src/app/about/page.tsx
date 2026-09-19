import Link from "next/link";

import { PageHeader } from "@/components/ui/PageHeader";

import styles from "./about.module.css";

export default function AboutPage() {
  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <PageHeader title="О проекте" description="KROMA — оперативный мониторинг природных пожаров." />
        <div className={styles.body}>
          <p>
            Сервис помогает пройти путь от территории и периода к термоточкам, контурам гарей, площади по степеням поражения
            и воспроизводимому экспорту через карту и REST API.
          </p>
          <p>
            Команда <strong>5BIT</strong> — разработка и ML/geospatial. Модельная часть ведётся отдельно; веб честно разделяет
            сценарий, live-источник и подготовленные наборы.
          </p>
          <section className={styles.section}>
            <h2>Территория мониторинга</h2>
            <p>
              Конкурсный охват — <strong>Нижнее Поволжье и Подонье</strong> (~435 тыс. км²): Ростовская, Волгоградская,
              Астраханская области, запад и центр Саратовской области, Республика Калмыкия. Сезоны 2019–2025, месяцы
              04–10. Граница АОИ и зоны UTM 37N/38N подключены к карте из датасета{" "}
              <a href="https://disk.yandex.ru/d/-rpmevTflbXZQg" target="_blank" rel="noreferrer">
                Мониторинг DATA
              </a>
              .
            </p>
            <p>
              Архивы train/test (чипы AF/BS) — для ML, не для live-слоя. Сибирские регионы в селекторе помечены как
              «сценарий» и не подменяют конкурсный AOI.
            </p>
          </section>
          <div className={styles.links}>
            <Link href="/">Обзор</Link>
            <Link href="/analytics?tab=area">Анализ территории</Link>
            <Link href="/explorer">Данные</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
