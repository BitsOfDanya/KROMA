import { PageHeader } from "@/components/ui/PageHeader";

import styles from "../about/about.module.css";

export default function ResearchPage() {
  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <PageHeader title="Research" description="Раздел в подготовке." />
        <div className={styles.body} />
      </div>
    </div>
  );
}
