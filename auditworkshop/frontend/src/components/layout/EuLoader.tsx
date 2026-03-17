export default function EuLoader({ message = 'Wird geladen...' }: { message?: string }) {
  return (
    <div className="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-gradient-to-br from-[#003399] via-[#002b80] to-[#001a4d]">
      {/* Animated EU Stars */}
      <div className="relative h-32 w-32 mb-8">
        {Array.from({ length: 12 }).map((_, i) => {
          const angle = (i * 30 - 90) * (Math.PI / 180);
          const x = 50 + 40 * Math.cos(angle);
          const y = 50 + 40 * Math.sin(angle);
          return (
            <div
              key={i}
              className="absolute animate-pulse"
              style={{
                left: `${x}%`,
                top: `${y}%`,
                transform: 'translate(-50%, -50%)',
                animationDelay: `${i * 100}ms`,
                animationDuration: '2s',
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                <path
                  d="M12 2l2.09 6.26L20.18 9l-5.09 3.74L16.18 19 12 15.27 7.82 19l1.09-6.26L3.82 9l6.09-.74L12 2z"
                  fill="#FFD700"
                  className="drop-shadow-[0_0_6px_rgba(255,215,0,0.8)]"
                />
              </svg>
            </div>
          );
        })}
        {/* Center glow */}
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="h-16 w-16 rounded-full bg-[#FFD700]/10 animate-ping" style={{ animationDuration: '3s' }} />
        </div>
      </div>
      <p className="text-sm font-medium text-white/80 tracking-wider uppercase">{message}</p>
      <div className="mt-4 flex gap-1">
        <div className="h-1.5 w-1.5 rounded-full bg-[#FFD700] animate-bounce" style={{ animationDelay: '0ms' }} />
        <div className="h-1.5 w-1.5 rounded-full bg-[#FFD700] animate-bounce" style={{ animationDelay: '150ms' }} />
        <div className="h-1.5 w-1.5 rounded-full bg-[#FFD700] animate-bounce" style={{ animationDelay: '300ms' }} />
      </div>
    </div>
  );
}
