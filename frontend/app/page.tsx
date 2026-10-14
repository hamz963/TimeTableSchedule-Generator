export default function Home() {
  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-bold">Time Table Schedule Generator</h1>
      <p className="text-gray-600 dark:text-gray-400">
        Generates conflict-free, optimized university schedules in under 5 seconds
        using OR-Tools CP-SAT. Handles real-time rescheduling with minimal disruption.
      </p>
      <p className="text-gray-600 dark:text-gray-400">
        Teachers: just enter <strong>teacher names</strong>, <strong>courses with credit
        hours</strong>, and the <strong>school day window</strong> — periods, gaps, lunch
        breaks, and fair spreading across the week are automatic.
      </p>
      <div className="flex flex-wrap gap-3">
        <a href="/data" className="rounded bg-blue-600 px-4 py-2 text-white">Load data & build</a>
        <a href="/schedule/easy" className="rounded border px-4 py-2">Easy Timetable Builder</a>
        <a href="/health" className="rounded border px-4 py-2">System health</a>
      </div>
    </div>
  );
}
