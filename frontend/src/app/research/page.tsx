import Link from "next/link";
import { PageHeader } from "@/components/ui/PageHeader";
import styles from "../about/about.module.css";

const scores = [
  ["v001", "0.5526"],
  ["v002", "0.6457"],
  ["v003", "0.7298"],
  ["v004", "0.7406"],
  ["v005", "0.8127"],
  ["v006 · CURRENT GOLD", "0.8176"],
];

export default function ResearchPage() {
  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <PageHeader
          title="Research"
          description="AF + BS · эволюция моделей и воспроизводимость"
        />
        <div className={styles.body}>
          <section className={styles.section}>
            <h2>Leaderboard</h2>
            <p>
              Public scores команды; это конкурсная метрика, не local TRAIN F1.
            </p>
            <table>
              <thead>
                <tr>
                  <th>Версия</th>
                  <th>Public score</th>
                </tr>
              </thead>
              <tbody>
                {scores.map(([version, score]) => (
                  <tr key={version}>
                    <td>{version}</td>
                    <td>{score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section className={styles.section}>
            <h2>Production pipeline</h2>
            <p>
              AF: LightGBM, 39 признаков VIIRS + AUX, threshold 0.765. BS:
              ансамбль U-Net v003 → physics / dNBR и refiner v004 → component
              filter и pixel refiner с red-edge признаками v006. Правила 0.3 /
              0.8 / 0.2 сохранены.
            </p>
          </section>
          <section className={styles.section}>
            <h2>Главные эксперименты</h2>
            <p>
              Thermal validity и hard negatives для AF; crop/context, OHEM,
              dual-head ensemble для BS; landcover-aware physics, component
              rejection, contour refinement и B5/B6/B7 / NDRE для границ гарей.
            </p>
          </section>
          <section className={styles.section}>
            <h2>Ограничения</h2>
            <p>
              TRAIN предсказания in-sample. TEST анонимизирован и на карту не
              наносится. Облака, смешанные пиксели и низкая severity остаются
              источниками ошибок. LIVE FIRMS — сырые детекции, а не AF
              inference. Competition inference выполняет только submission;
              геометрии строятся отдельно в сервисе.
            </p>
            <p>
              Подробный протокол, OOF и история экспериментов:
              research/report.md. Артефакты и SHA256:
              ml/artifacts/manifest.json.
            </p>
          </section>
          <div className={styles.links}>
            <Link href="/predict">Проверить модель</Link>
            <Link href="/explorer">Official TRAIN</Link>
            <Link href="/about">О проекте</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
