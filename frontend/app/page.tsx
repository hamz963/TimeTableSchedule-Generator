export default function Home() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-3xl font-bold">Time Table Schedule Generator</h1>
        <p className="text-gray-600 dark:text-gray-400">
          An optimization engine (OR-Tools CP-SAT for exact search + a
          simulated-annealing metaheuristic for large instances) that produces
          conflict-free, high-quality university timetables in seconds.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card title="Optimized, not just feasible" href="/benchmark" link="Run benchmark">
          Every timetable gets a 0–100 quality score across teacher preferences,
          time-of-day fit, room efficiency, fairness and compactness — with a
          benchmark proving the optimizer's gain over a greedy baseline.
        </Card>
        <Card title="Rules that actually apply" href="/constraints" link="Constraints">
          Declarative rules — <em>course before course</em>, <em>no Friday labs</em>,
          <em> these courses share a day</em> — are compiled into the solver and
          audited on every result.
        </Card>
        <Card title="Live + explainable" href="/schedule/easy" link="Build a timetable">
          Watch schedules update in real time over Server-Sent Events, and read a
          plain-language explanation of why each timetable looks the way it does.
        </Card>
      </div>

      <div className="flex flex-wrap gap-3">
        <a href="/data" className="rounded bg-blue-600 px-4 py-2 text-white">
          Load data &amp; build
        </a>
        <a href="/schedule/easy" className="rounded border px-4 py-2">
          Easy Timetable Builder
        </a>
        <a href="/benchmark" className="rounded border px-4 py-2">
          Optimizer benchmark
        </a>
        <a href="/health" className="rounded border px-4 py-2">
          System health
        </a>
      </div>
    </div>
  );
}

function Card({
  title,
  href,
  link,
  children,
}: {
  title: string;
  href: string;
  link: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col justify-between rounded-lg border bg-white p-4 shadow-sm dark:bg-gray-900">
      <div className="space-y-2">
        <h2 className="font-semibold">{title}</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400">{children}</p>
      </div>
      <a href={href} className="mt-3 text-sm text-blue-600 hover:underline">
        {link} →
      </a>
    </div>
  );
}
