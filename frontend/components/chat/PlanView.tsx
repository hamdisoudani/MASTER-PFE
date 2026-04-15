'use client';

import styles from './PlanView.module.css';

interface PlanViewProps {
  steps: string[];
}

export function PlanView({ steps }: PlanViewProps): React.JSX.Element {
  return (
    <ol className={styles.list}>
      {steps.map((step, index) => (
        <li key={index} className={styles.item}>
          <span className={styles.index}>{index + 1}</span>
          <span className={styles.text}>{step}</span>
        </li>
      ))}
    </ol>
  );
}
