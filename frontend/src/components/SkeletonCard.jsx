export default function SkeletonCard() {
  return (
    <div style={{
      background: '#0d1117', border: '1px solid #21262d',
      borderRadius: 10, padding: 0, overflow: 'hidden',
    }}>
      <style>{`
        @keyframes shimmer {
          0%   { background-position: -400px 0; }
          100% { background-position: 400px 0; }
        }
      `}</style>

      {/* Header skeleton */}
      <div style={{ padding: '10px 14px 8px', display: 'flex', justifyContent: 'space-between' }}>
        <div>
          <ShimmerBlock w={60} h={16} />
          <div style={{ marginTop: 4 }}>
            <ShimmerBlock w={90} h={10} />
          </div>
        </div>
        <ShimmerBlock w={70} h={22} radius={5} />
      </div>

      {/* Score skeleton */}
      <div style={{ padding: '10px 14px 8px', textAlign: 'center' }}>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 2 }}>
          <ShimmerBlock w={50} h={26} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'center', marginTop: 4 }}>
          <ShimmerBlock w={80} h={9} />
        </div>
        <div style={{ marginTop: 6 }}>
          <ShimmerBlock w="100%" h={4} radius={3} />
        </div>
      </div>

      {/* Metrics skeleton */}
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr 1fr',
        borderTop: '1px solid #21262d', borderBottom: '1px solid #21262d',
        padding: '5px 4px',
      }}>
        {[0, 1, 2].map(i => (
          <div key={i} style={{ textAlign: 'center', padding: '5px 4px' }}>
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 2 }}>
              <ShimmerBlock w={36} h={9} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'center' }}>
              <ShimmerBlock w={44} h={12} />
            </div>
          </div>
        ))}
      </div>

      {/* Chart skeleton */}
      <div style={{ padding: '8px 14px 4px' }}>
        <div style={{ marginBottom: 6 }}>
          <ShimmerBlock w={100} h={10} />
        </div>
        <div style={{
          height: 90, display: 'flex', alignItems: 'flex-end', gap: 3,
          justifyContent: 'space-between', padding: '0 3px',
        }}>
          {[40, 70, 55, 90, 50, 35, 60, 80].map((h, i) => (
            <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
              <div style={{
                width: '100%', height: `${h}%`,
                background: 'linear-gradient(90deg, #161b22 0%, #21262d 50%, #161b22 100%)',
                backgroundSize: '800px 100%',
                animation: 'shimmer 1.5s ease-in-out infinite',
                borderRadius: 3,
              }} />
              <div style={{ width: '100%', height: 7, background: '#161b22', borderRadius: 2 }} />
            </div>
          ))}
        </div>
      </div>

      {/* Actions skeleton */}
      <div style={{ padding: '8px 14px 6px', display: 'flex', gap: 6 }}>
        <ShimmerBlock w="50%" h={26} radius={5} />
        <ShimmerBlock w="50%" h={26} radius={5} />
      </div>

      {/* Conviction skeleton */}
      <div style={{ padding: '4px 14px 10px', display: 'flex', justifyContent: 'center' }}>
        <ShimmerBlock w={110} h={18} radius={3} />
      </div>
    </div>
  );
}

function ShimmerBlock({ w, h, radius = 3 }) {
  return (
    <div style={{
      width: w,
      height: h,
      borderRadius: radius,
      background: 'linear-gradient(90deg, #161b22 0%, #21262d 50%, #161b22 100%)',
      backgroundSize: '800px 100%',
      animation: 'shimmer 1.5s ease-in-out infinite',
    }} />
  );
}
