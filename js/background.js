export function initLowerBackground() {
  const canvas = document.getElementById('lower-bg-canvas');
  const lowerWorld = document.getElementById('lower-world');
  if (!canvas) return;

  const ctx = canvas.getContext('2d', { alpha: false });
  let targetX = 0.5;
  let targetY = 0.35;
  let mx = 0.5;
  let my = 0.35;
  let isVisible = true;
  let rafId = null;

  window.addEventListener(
    'pointermove',
    (e) => {
      targetX = e.clientX / Math.max(1, window.innerWidth);
      targetY = e.clientY / Math.max(1, window.innerHeight);
    },
    { passive: true }
  );

  function render(now) {
    if (!isVisible) {
      rafId = null;
      return;
    }
    rafId = requestAnimationFrame(render);

    const t = now * 0.001;
    // Soft radial aurora blurs look identical at 0.5x resolution while saving ~9x fillrate
    const scale = 0.5;
    const W = Math.max(1, Math.floor(window.innerWidth * scale));
    const H = Math.max(1, Math.floor(window.innerHeight * scale));

    if (canvas.width !== W || canvas.height !== H) {
      canvas.width = W;
      canvas.height = H;
    }

    // Smoothly interpolate cursor spotlight
    mx += (targetX - mx) * 0.08;
    my += (targetY - my) * 0.08;

    ctx.fillStyle = '#05060b';
    ctx.fillRect(0, 0, W, H);

    // Fluid Neon Aurora Mesh + Cursor Spotlight (Variant 2)
    const blobs = [
      {
        x: 0.22 + Math.sin(t * 0.5) * 0.14,
        y: 0.3 + Math.cos(t * 0.4) * 0.14,
        c: 'rgba(168, 85, 247, 0.30)',
        r: 0.54
      },
      {
        x: 0.78 + Math.cos(t * 0.45) * 0.14,
        y: 0.7 + Math.sin(t * 0.55) * 0.14,
        c: 'rgba(0, 245, 212, 0.24)',
        r: 0.54
      },
      {
        x: mx,
        y: my,
        c: 'rgba(168, 85, 247, 0.22)',
        r: 0.34
      }
    ];

    const maxDim = Math.max(W, H);
    for (const b of blobs) {
      const g = ctx.createRadialGradient(b.x * W, b.y * H, 4, b.x * W, b.y * H, b.r * maxDim);
      g.addColorStop(0, b.c);
      g.addColorStop(1, 'transparent');
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, W, H);
    }
  }

  function resume() {
    if (isVisible && rafId === null) {
      rafId = requestAnimationFrame(render);
    }
  }

  if (lowerWorld && typeof IntersectionObserver !== 'undefined') {
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          isVisible = entry.isIntersecting;
          if (isVisible) resume();
        }
      },
      { rootMargin: '250px 0px', threshold: 0.0 }
    );
    io.observe(lowerWorld);
  }

  resume();
}
