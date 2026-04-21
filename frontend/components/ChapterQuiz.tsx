"use client";
/**
 * ChapterQuiz — renders a `ChapterActivity` of kind="quiz" and verifies the
 * learner's answers locally by comparing against `correct_choice_ids` stored
 * in the payload. No backend submission — this is the MVP the syllabus agent
 * targets: the agent emits the answer key as JSON, the frontend does the
 * scoring client-side.
 */
import { useMemo, useState } from "react";
import type {
  ChapterActivity,
  QuizQuestion,
} from "@/store/syllabusStore";

interface Props {
  activity: ChapterActivity;
  onSubmitted?: (result: { score: number; total: number; perQuestion: Record<string, boolean> }) => void;
}

function arraysEqualAsSets(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const s = new Set(a);
  for (const x of b) if (!s.has(x)) return false;
  return true;
}

function gradeQuestion(q: QuizQuestion, picked: string[]): boolean {
  if (!picked.length) return false;
  if (q.kind === "multi") return arraysEqualAsSets(picked, q.correct_choice_ids);
  return picked.length === 1 && q.correct_choice_ids.includes(picked[0]);
}

export default function ChapterQuiz({ activity, onSubmitted }: Props) {
  const questions = activity.payload?.questions ?? [];
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const [submitted, setSubmitted] = useState(false);

  const results = useMemo(() => {
    if (!submitted) return null;
    const perQuestion: Record<string, boolean> = {};
    let score = 0;
    for (const q of questions) {
      const ok = gradeQuestion(q, answers[q.id] ?? []);
      perQuestion[q.id] = ok;
      if (ok) score += 1;
    }
    return { score, total: questions.length, perQuestion };
  }, [submitted, answers, questions]);

  function toggleChoice(q: QuizQuestion, choiceId: string) {
    if (submitted) return;
    setAnswers((prev) => {
      const current = prev[q.id] ?? [];
      if (q.kind === "multi") {
        const next = current.includes(choiceId)
          ? current.filter((c) => c !== choiceId)
          : [...current, choiceId];
        return { ...prev, [q.id]: next };
      }
      return { ...prev, [q.id]: [choiceId] };
    });
  }

  function handleSubmit() {
    setSubmitted(true);
    if (onSubmitted && questions.length) {
      const perQuestion: Record<string, boolean> = {};
      let score = 0;
      for (const q of questions) {
        const ok = gradeQuestion(q, answers[q.id] ?? []);
        perQuestion[q.id] = ok;
        if (ok) score += 1;
      }
      onSubmitted({ score, total: questions.length, perQuestion });
    }
  }

  function handleReset() {
    setAnswers({});
    setSubmitted(false);
  }

  if (!questions.length) {
    return (
      <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
        This quiz has no questions yet.
      </div>
    );
  }

  return (
    <section className="flex flex-col gap-4 rounded-xl border bg-card p-4 shadow-sm">
      <header className="flex items-baseline justify-between gap-2">
        <h3 className="text-base font-semibold">{activity.title}</h3>
        <span className="text-xs uppercase tracking-wide text-muted-foreground">
          Quiz · {questions.length} question{questions.length === 1 ? "" : "s"}
        </span>
      </header>

      {activity.payload?.instructions ? (
        <p className="text-sm text-muted-foreground">{activity.payload.instructions}</p>
      ) : null}

      <ol className="flex flex-col gap-4">
        {questions.map((q, idx) => {
          const picked = answers[q.id] ?? [];
          const graded = submitted ? results?.perQuestion[q.id] : null;
          return (
            <li key={q.id} className="flex flex-col gap-2 rounded-lg border p-3">
              <div className="flex items-start gap-2">
                <span className="text-sm font-medium text-muted-foreground">{idx + 1}.</span>
                <p className="text-sm font-medium">{q.prompt}</p>
                {submitted ? (
                  <span
                    className={
                      "ml-auto rounded-full px-2 py-0.5 text-xs font-semibold " +
                      (graded ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700")
                    }
                  >
                    {graded ? "Correct" : "Incorrect"}
                  </span>
                ) : null}
              </div>
              <ul className="flex flex-col gap-1.5 pl-6">
                {q.choices.map((c) => {
                  const selected = picked.includes(c.id);
                  const isAnswer = q.correct_choice_ids.includes(c.id);
                  const feedbackClass = submitted
                    ? isAnswer
                      ? "border-emerald-500 bg-emerald-50"
                      : selected
                      ? "border-rose-500 bg-rose-50"
                      : "border-transparent"
                    : selected
                    ? "border-primary bg-primary/5"
                    : "border-transparent hover:border-muted";
                  const inputType = q.kind === "multi" ? "checkbox" : "radio";
                  return (
                    <li key={c.id}>
                      <label
                        className={
                          "flex cursor-pointer items-center gap-2 rounded-md border px-2 py-1.5 text-sm transition-colors " +
                          feedbackClass
                        }
                      >
                        <input
                          type={inputType}
                          name={`q-${q.id}`}
                          checked={selected}
                          disabled={submitted}
                          onChange={() => toggleChoice(q, c.id)}
                        />
                        <span>{c.text}</span>
                        {submitted && isAnswer ? (
                          <span className="ml-auto text-xs font-semibold text-emerald-700">answer</span>
                        ) : null}
                      </label>
                    </li>
                  );
                })}
              </ul>
              {submitted && q.explanation ? (
                <p className="pl-6 text-xs text-muted-foreground">{q.explanation}</p>
              ) : null}
            </li>
          );
        })}
      </ol>

      <footer className="flex items-center justify-between gap-2">
        {submitted && results ? (
          <p className="text-sm font-medium">
            Score: {results.score} / {results.total}
          </p>
        ) : (
          <span className="text-xs text-muted-foreground">
            Answers are verified locally against the agent-provided key.
          </span>
        )}
        <div className="flex gap-2">
          {submitted ? (
            <button
              type="button"
              onClick={handleReset}
              className="rounded-md border px-3 py-1.5 text-sm hover:bg-muted"
            >
              Try again
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSubmit}
              disabled={Object.keys(answers).length === 0}
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              Submit
            </button>
          )}
        </div>
      </footer>
    </section>
  );
}
