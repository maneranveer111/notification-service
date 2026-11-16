export default function Loading({ text = 'Loading…', className = '' }) {
  return (
    <div
      className={`flex flex-col items-center justify-center py-16 gap-3 text-[#78716C] ${className}`}
    >
      <div className="w-5 h-5 rounded-full border-2 border-[#E7E5E4] border-t-[#4F46E5] animate-spin" />
      <span className="text-xs">{text}</span>
    </div>
  );
}
