import * as THREE from 'three';
import { buildDrawbridgeGeometry } from './geometries.js';

export function createHeroScene({ canvas, heroEl, loaderEl }) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
  renderer.setClearColor(0x000000, 1);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 100);
  camera.position.set(0, 0, 10);
  camera.lookAt(0, 0, 0);

  const scene = new THREE.Scene();
  const pivot = new THREE.Group();
  const spinner = new THREE.Group();
  spinner.rotation.set(-0.14, 0.34, 0.0);
  pivot.add(spinner);
  scene.add(pivot);

  // Locked-in user configuration
  const state = {
    presetId: 'xray',
    mode: 5,
    r: 168,
    g: 85,
    b: 247,
    r2: 0,
    g2: 245,
    b2: 212,
    gradAngleDeg: 51,
    colorMix: 0.92,
    bodyBright: 0.04,
    refract: 0.2,
    fresnel: 1.6,
    frost: 0.5,
    chromatic: 0,
    modelScale: 1.02,
    modelOffsetY: 0.03,
    bgText: 'INSTALL\nCONNECT\nCONTROL',
    textScale: 0.76,
    textGap: 0.9,
    textOpacity: 1
  };

  // Background 2D canvas + fullscreen quad
  const bgCanvas = document.createElement('canvas');
  const bgCtx = bgCanvas.getContext('2d');
  let bgTex = new THREE.CanvasTexture(bgCanvas);
  bgTex.colorSpace = THREE.SRGBColorSpace;
  bgTex.minFilter = THREE.LinearFilter;
  bgTex.magFilter = THREE.LinearFilter;
  bgTex.generateMipmaps = false;

  const bgScene = new THREE.Scene();
  const bgCamera = new THREE.Camera();
  const bgMat = new THREE.ShaderMaterial({
    uniforms: {
      uTex: { value: bgTex }
    },
    vertexShader: `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = vec4(position.xy, 0.0, 1.0);
      }
    `,
    fragmentShader: `
      uniform sampler2D uTex;
      varying vec2 vUv;
      void main() {
        gl_FragColor = texture2D(uTex, vUv);
        #include <colorspace_fragment>
      }
    `,
    depthTest: false,
    depthWrite: false
  });
  const bgQuad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), bgMat);
  bgQuad.frustumCulled = false;
  bgScene.add(bgQuad);

  // Render targets for two-pass optical refraction
  const rtBack = new THREE.WebGLRenderTarget(1, 1, {
    type: THREE.HalfFloatType,
    minFilter: THREE.LinearFilter,
    magFilter: THREE.LinearFilter
  });
  const rtFront = new THREE.WebGLRenderTarget(1, 1, {
    type: THREE.HalfFloatType,
    minFilter: THREE.LinearFilter,
    magFilter: THREE.LinearFilter
  });

  const glassVertexShader = `
    varying vec3 vNormal;
    varying vec3 vEye;
    varying vec3 vLocalPos;
    void main() {
      vLocalPos = position;
      vec4 worldPos = modelMatrix * vec4(position, 1.0);
      vec4 mvPos = viewMatrix * worldPos;
      gl_Position = projectionMatrix * mvPos;
      vNormal = normalize(normalMatrix * normal);
      vEye = normalize(mvPos.xyz);
    }
  `;

  // X-Ray Edge Glow + Dual-RGB Gradient Optical Refraction Shader
  const glassFragmentShader = `
    uniform sampler2D uTexture;
    uniform vec2 uResolution;
    uniform float uIorG;
    uniform float uRefractPower;
    uniform float uBlurSpread;
    uniform float uBodyBright;
    uniform float uShininess;
    uniform float uDiffuseness;
    uniform float uFresnelPower;
    uniform vec3 uLight;
    uniform vec3 uColor1;
    uniform vec3 uColor2;
    uniform float uColorMix;
    uniform float uGradAngle;
    uniform float uBackside;

    varying vec3 vNormal;
    varying vec3 vEye;
    varying vec3 vLocalPos;

    float calcSpecular(vec3 eye, vec3 n, vec3 light, float shininess, float diffuseness) {
      vec3 lightVec = normalize(-light);
      vec3 viewVec = -eye;
      vec3 halfVec = normalize(lightVec + viewVec);
      float specSharp = pow(max(dot(n, halfVec), 0.0), shininess);
      float specBroad = pow(max(dot(n, halfVec), 0.0), 14.0) * 0.38;
      float diff = max(dot(n, lightVec), 0.0) * diffuseness;
      return specSharp + specBroad + diff;
    }

    void main() {
      vec2 uv = gl_FragCoord.xy / uResolution;
      vec3 n = normalize(vNormal);
      if (uBackside > 0.5) n = -n;
      vec3 eye = normalize(vEye);

      vec3 refrColor = vec3(0.0);
      const int LOOP = 16;
      vec3 refr = refract(eye, n, 1.0 / uIorG);
      for (int i = 0; i < LOOP; i++) {
        float t = (float(i) / float(LOOP) - 0.5);
        vec2 offset = refr.xy * uRefractPower + vec2(t, t * 0.65) * 0.032 * uBlurSpread;
        vec4 texSample = texture2D(uTexture, uv + offset);
        refrColor += texSample.rgb;
      }
      refrColor /= float(LOOP);
      float refrLuma = dot(refrColor, vec3(0.299, 0.587, 0.114));

      float studioKey = calcSpecular(eye, n, uLight, uShininess, uDiffuseness);
      float f = pow(clamp(1.0 + dot(eye, n), 0.0, 1.0), uFresnelPower);

      float ca = cos(uGradAngle);
      float sa = sin(uGradAngle);
      float linearT = clamp((vLocalPos.x * ca + vLocalPos.y * sa) * 1.15 + 0.5, 0.0, 1.0);

      vec3 c1 = mix(vec3(1.0), uColor1, uColorMix);
      vec3 c2 = mix(vec3(0.75), uColor2, uColorMix);

      float core = uBodyBright * 0.5 + refrLuma * 0.55;
      vec3 finalColor = vec3(core) * c1;
      finalColor += studioKey * 0.7 * c1;
      finalColor = mix(finalColor, mix(c1, c2, linearT) * 1.18, f * (uBackside > 0.5 ? 0.55 : 0.95));

      gl_FragColor = vec4(clamp(finalColor, 0.0, 1.0), 1.0);
      #include <colorspace_fragment>
    }
  `;

  function createGlassMaterial({ texture, refractScale, backside, side }) {
    return new THREE.ShaderMaterial({
      uniforms: {
        uTexture: { value: texture },
        uResolution: { value: new THREE.Vector2(1, 1) },
        uIorG: { value: 1.18 },
        uRefractPower: { value: state.refract * refractScale },
        uBlurSpread: { value: state.frost },
        uBodyBright: { value: state.bodyBright },
        uShininess: { value: 85.0 },
        uDiffuseness: { value: 0.16 },
        uFresnelPower: { value: state.fresnel },
        uLight: { value: new THREE.Vector3(-0.8, 0.9, 1.0) },
        uColor1: { value: new THREE.Color(state.r / 255, state.g / 255, state.b / 255) },
        uColor2: { value: new THREE.Color(state.r2 / 255, state.g2 / 255, state.b2 / 255) },
        uColorMix: { value: state.colorMix },
        uGradAngle: { value: THREE.MathUtils.degToRad(state.gradAngleDeg) },
        uBackside: { value: backside }
      },
      vertexShader: glassVertexShader,
      fragmentShader: glassFragmentShader,
      side
    });
  }

  const backMat = createGlassMaterial({
    texture: rtBack.texture,
    refractScale: 0.74,
    backside: 1.0,
    side: THREE.BackSide
  });
  const frontMat = createGlassMaterial({
    texture: rtFront.texture,
    refractScale: 1.0,
    backside: 0.0,
    side: THREE.FrontSide
  });

  const drawbridgeGeom = buildDrawbridgeGeometry();
  const bridgeMesh = new THREE.Mesh(drawbridgeGeom, frontMat);
  spinner.add(bridgeMesh);
  if (loaderEl) loaderEl.classList.add('done');

  const drawBuf = new THREE.Vector2();
  let viewW = 1;
  let viewH = 1;

  /**
   * Computes safe visual stage center and scale between the top nav and bottom UI bar
   * so the 3D bridge and background typography never collide with UI text on any aspect ratio.
   */
  function getStageMetrics(W, H) {
    const narrow = W <= 768;
    const topSafe = narrow ? 96 : 84;
    const bottomSafe = narrow ? 175 : 138;
    const availH = Math.max(200, H - topSafe - bottomSafe);
    const centerY = topSafe + availH * 0.48;
    const sy = centerY / Math.max(1, H);
    const sx = narrow ? 0.5 : 0.51;
    return { narrow, availH, sx, sy };
  }

  function applyTransform() {
    const aspect = viewW / Math.max(1, viewH);
    const { narrow, availH, sx, sy } = getStageMetrics(viewW, viewH);
    const fovRad = THREE.MathUtils.degToRad(camera.fov);
    const visH = 2 * Math.tan(fovRad / 2) * 10;
    const visW = visH * aspect;

    const targetSy = sy - state.modelOffsetY * (availH / Math.max(1, viewH));
    pivot.position.set((sx - 0.5) * visW, (0.5 - targetSy) * visH, 0);

    const px = Math.min(availH * 0.72, viewW * (narrow ? 0.72 : 0.34)) * state.modelScale;
    pivot.scale.setScalar((px / Math.max(1, viewH)) * visH);
  }

  function drawHeadline(W, H, bufW, bufH) {
    const sizeChanged = bgCanvas.width !== bufW || bgCanvas.height !== bufH;
    if (sizeChanged) {
      bgCanvas.width = bufW;
      bgCanvas.height = bufH;
    }

    bgCtx.setTransform(bufW / W, 0, 0, bufH / H, 0, 0);
    bgCtx.fillStyle = '#000';
    bgCtx.fillRect(0, 0, W, H);

    const rawLines = state.bgText
      .split(/\r?\n|\|/)
      .map((s) => s.trim())
      .filter(Boolean);

    if (rawLines.length > 0) {
      const { narrow, availH, sx, sy } = getStageMetrics(W, H);
      let fs = Math.min(availH * 0.31, W * (narrow ? 0.21 : 0.135)) * state.textScale;
      const maxW = W * (narrow ? 0.88 : 0.68);

      bgCtx.font = `800 ${fs}px Poppins, sans-serif`;
      let widest = 0;
      for (const line of rawLines) {
        widest = Math.max(widest, bgCtx.measureText(line).width);
      }
      if (widest > maxW && widest > 0) {
        fs *= maxW / widest;
        bgCtx.font = `800 ${fs}px Poppins, sans-serif`;
      }

      const cx = W * sx;
      const cy = H * sy;
      const gap = fs * state.textGap;
      const cap = fs * 0.7;
      const mid = (rawLines.length - 1) * 0.5;

      const gray = Math.round(255 * Math.max(0, Math.min(1, state.textOpacity)));
      bgCtx.fillStyle = `rgb(${gray}, ${gray}, ${gray})`;
      bgCtx.textAlign = 'center';
      bgCtx.textBaseline = 'alphabetic';

      for (let i = 0; i < rawLines.length; i++) {
        const y = cy + cap / 2 + (i - mid) * gap;
        bgCtx.fillText(rawLines[i], cx, y);
      }
    }

    if (sizeChanged) {
      bgTex.dispose();
      bgTex = new THREE.CanvasTexture(bgCanvas);
      bgTex.colorSpace = THREE.SRGBColorSpace;
      bgTex.minFilter = THREE.LinearFilter;
      bgTex.magFilter = THREE.LinearFilter;
      bgTex.generateMipmaps = false;
      bgMat.uniforms.uTex.value = bgTex;
    } else {
      bgTex.needsUpdate = true;
    }
  }

  function layout() {
    viewW = Math.max(1, heroEl.clientWidth);
    viewH = Math.max(1, heroEl.clientHeight);

    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(viewW, viewH, false);
    renderer.getDrawingBufferSize(drawBuf);

    const aspect = viewW / viewH;
    camera.aspect = aspect;
    camera.updateProjectionMatrix();

    rtBack.setSize(drawBuf.x, drawBuf.y);
    rtFront.setSize(drawBuf.x, drawBuf.y);
    backMat.uniforms.uResolution.value.copy(drawBuf);
    frontMat.uniforms.uResolution.value.copy(drawBuf);

    drawHeadline(viewW, viewH, drawBuf.x, drawBuf.y);
    applyTransform();
  }

  // Interaction & animation state
  const X_AXIS = new THREE.Vector3(1, 0, 0);
  const Y_AXIS = new THREE.Vector3(0, 1, 0);
  const qTmp = new THREE.Quaternion();

  let isDragging = false;
  let activePointerId = null;
  let lastX = 0;
  let lastY = 0;
  let lastMoveTime = 0;
  let velX = 0;
  let velY = 0;
  let releaseTime = -Infinity;

  // Pause heavy 2-pass WebGL loop when #hero is scrolled completely offscreen
  let isHeroVisible = true;
  let rafId = null;

  function rotateWorld(dx, dy) {
    if (dx !== 0) {
      qTmp.setFromAxisAngle(Y_AXIS, dx);
      spinner.quaternion.premultiply(qTmp);
    }
    if (dy !== 0) {
      qTmp.setFromAxisAngle(X_AXIS, dy);
      spinner.quaternion.premultiply(qTmp);
    }
    spinner.quaternion.normalize();
  }

  canvas.addEventListener('pointerdown', (e) => {
    if (e.button !== undefined && e.button !== 0 && e.pointerType === 'mouse') return;
    isDragging = true;
    activePointerId = e.pointerId;
    try {
      canvas.setPointerCapture(e.pointerId);
    } catch {
      // Ignore if pointer capture is unavailable
    }
    canvas.classList.add('dragging');
    lastX = e.clientX;
    lastY = e.clientY;
    lastMoveTime = performance.now();
    velX = 0;
    velY = 0;
  });

  canvas.addEventListener('pointermove', (e) => {
    if (!isDragging || e.pointerId !== activePointerId) return;
    const sens = 4.6 / Math.max(360, Math.min(viewW, viewH));
    const dx = (e.clientX - lastX) * sens;
    const dy = (e.clientY - lastY) * sens;
    lastX = e.clientX;
    lastY = e.clientY;

    rotateWorld(dx, dy);

    const now = performance.now();
    const elapsed = Math.max(now - lastMoveTime, 6);
    const frames = Math.max(elapsed / 16.6667, 0.35);
    velX = velX * 0.35 + (dx / frames) * 0.65;
    velY = velY * 0.35 + (dy / frames) * 0.65;
    lastMoveTime = now;
  });

  function endDrag(e) {
    if (!isDragging || e.pointerId !== activePointerId) return;
    isDragging = false;
    canvas.classList.remove('dragging');
    try {
      if (canvas.hasPointerCapture(e.pointerId)) {
        canvas.releasePointerCapture(e.pointerId);
      }
    } catch {
      // Ignore
    }
    activePointerId = null;
    if (performance.now() - lastMoveTime > 90) {
      velX = 0;
      velY = 0;
    }
    releaseTime = performance.now();
  }

  canvas.addEventListener('pointerup', endDrag);
  canvas.addEventListener('pointercancel', endDrag);
  canvas.addEventListener('lostpointercapture', endDrag);

  if (typeof ResizeObserver !== 'undefined') {
    const ro = new ResizeObserver(() => layout());
    ro.observe(heroEl);
  } else {
    window.addEventListener('resize', layout);
  }

  if (document.fonts && document.fonts.addEventListener) {
    document.fonts.addEventListener('loadingdone', () => {
      if (drawBuf.x > 0 && drawBuf.y > 0) {
        drawHeadline(viewW, viewH, drawBuf.x, drawBuf.y);
      }
    });
  }

  let prevFrameTime = performance.now();
  function animate(now) {
    if (!isHeroVisible) {
      rafId = null;
      return;
    }
    rafId = requestAnimationFrame(animate);
    const dt = Math.min(Math.max((now - prevFrameTime) / 1000, 0), 0.05);
    prevFrameTime = now;
    const frames = dt * 60;

    if (!isDragging) {
      if (velX !== 0 || velY !== 0) {
        rotateWorld(velX * frames, velY * frames);
        const damp = Math.pow(0.94, frames);
        velX *= damp;
        velY *= damp;
        if (Math.abs(velX) < 1e-6 && Math.abs(velY) < 1e-6) {
          velX = 0;
          velY = 0;
        }
      }

      const sinceRelease = (now - releaseTime) / 1000;
      if (sinceRelease > 0.6) {
        const blend = Math.min(1, sinceRelease - 0.6);
        rotateWorld(0.0032 * frames * blend, 0.0008 * frames * blend);
      }
    }

    // Pass 1: background -> rtBack
    renderer.setRenderTarget(rtBack);
    renderer.render(bgScene, bgCamera);

    // Pass 2: background + back faces -> rtFront
    renderer.setRenderTarget(rtFront);
    renderer.render(bgScene, bgCamera);
    if (bridgeMesh) {
      bridgeMesh.material = backMat;
      renderer.autoClear = false;
      renderer.render(scene, camera);
      renderer.autoClear = true;
    }

    // Pass 3: background + front faces -> screen
    renderer.setRenderTarget(null);
    renderer.render(bgScene, bgCamera);
    if (bridgeMesh) {
      bridgeMesh.material = frontMat;
      renderer.autoClear = false;
      renderer.clearDepth();
      renderer.render(scene, camera);
      renderer.autoClear = true;
    }
  }

  function resumeLoop() {
    if (isHeroVisible && rafId === null) {
      prevFrameTime = performance.now();
      rafId = requestAnimationFrame(animate);
    }
  }

  if (typeof IntersectionObserver !== 'undefined') {
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          isHeroVisible = entry.isIntersecting;
          if (isHeroVisible) resumeLoop();
        }
      },
      { threshold: 0.01 }
    );
    io.observe(heroEl);
  }

  function start() {
    const fontWait = document.fonts
      ? Promise.race([
          Promise.all([document.fonts.load('800 100px Poppins'), document.fonts.ready]),
          new Promise((resolve) => setTimeout(resolve, 2000))
        ])
      : Promise.resolve();

    fontWait.then(() => {
      layout();
      resumeLoop();
    });
  }

  return {
    start
  };
}
