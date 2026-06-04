interface StatCardProps {
  label: string;
  value: string | number;
}

export function StatCard({ label, value }: StatCardProps) {
  return (
    <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
      <p className="text-slate-400 text-sm">{label}</p>
      <p className="text-2xl font-semibold mt-1">{value}</p>
    </div>
  );
}
