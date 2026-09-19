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
