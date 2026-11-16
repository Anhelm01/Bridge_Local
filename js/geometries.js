import * as THREE from 'three';
import { mergeVertices, mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

/**
 * Normalizes any BufferGeometry using the exact pipeline from the reference:
 * strips extra attributes, merges vertices, computes smooth normals,
 * centers bounding box, and scales to unit max dimension.
 */
export function normalizeGlassGeometry(parts) {
  const cleanParts = parts.map((geom) => {
    let g = geom.index ? geom.toNonIndexed() : geom.clone();
    const keep = new Set(['position', 'normal']);
    for (const name of Object.keys(g.attributes)) {
      if (!keep.has(name)) {
        g.deleteAttribute(name);
      }
    }
    return g;
  });

  let merged = cleanParts.length === 1 ? cleanParts[0] : mergeGeometries(cleanParts, false);
  merged = mergeVertices(merged, 1e-4);
  merged.computeVertexNormals();

  merged.computeBoundingBox();
  const box = merged.boundingBox;
  const center = new THREE.Vector3();
  const size = new THREE.Vector3();
  box.getCenter(center);
  box.getSize(size);
  merged.translate(-center.x, -center.y, -center.z);
  const maxDim = Math.max(size.x, size.y, size.z) || 1;
  merged.scale(1 / maxDim, 1 / maxDim, 1 / maxDim);

  return merged;
}

/**
 * Helper to extrude a 2D polygon (array of [x, y] points) centered along Z
 * with smooth optical bevels so light refracts cleanly across every edge.
 */
function createExtrudedPolygon(points, depth, bevelSize = 0.022, bevelSegments = 5, zOffset = 0) {
  const shape = new THREE.Shape();
  shape.moveTo(points[0][0], points[0][1]);
  for (let i = 1; i < points.length; i++) {
    shape.lineTo(points[i][0], points[i][1]);
  }
  shape.closePath();

  const geom = new THREE.ExtrudeGeometry(shape, {
    depth,
    bevelEnabled: true,
    bevelThickness: bevelSize,
    bevelSize,
    bevelSegments,
    curveSegments: 24
  });

  geom.translate(0, 0, -depth * 0.5 + zOffset);
  return geom;
}

/**
 * Builds the Minimalist 3D Drawbridge ("Разводной мост в минимализме")
 * faithfully following the architectural silhouette of the reference emblem
 * with true 3D architectural depth along Z.
 */
export function buildDrawbridgeGeometry() {
  const parts = [];

  // 1. Overarching Semi-Circular Halo Arch + Horizontal Base Shoulders
  // Center of arc at (0, 0.14), outer radius = 1.18, inner radius = 1.115
  const archShape = new THREE.Shape();
  const outerR = 1.18;
  const innerR = 1.115;
  const cy = 0.14;
  const arcSegments = 64;

  // Start at right shoulder outer corner (1.18, 0.14) and trace upper semi-circle to (-1.18, 0.14)
  for (let i = 0; i <= arcSegments; i++) {
    const a = (i / arcSegments) * Math.PI;
    const x = Math.cos(a) * outerR;
    const y = cy + Math.sin(a) * outerR * 0.76;
    if (i === 0) archShape.moveTo(x, y);
    else archShape.lineTo(x, y);
  }
  // Left horizontal shoulder inward (-1.18 -> -0.90)
  archShape.lineTo(-0.90, cy);
  archShape.lineTo(-0.90, cy + 0.052);
  archShape.lineTo(-innerR, cy + 0.052);

  // Inner arc from left to right
  for (let i = arcSegments - 1; i >= 1; i--) {
    const a = (i / arcSegments) * Math.PI;
    const x = Math.cos(a) * innerR;
    const y = cy + Math.sin(a) * innerR * 0.76;
    archShape.lineTo(x, y);
  }

  // Right horizontal shoulder inward (innerR -> 0.90)
  archShape.lineTo(innerR, cy + 0.052);
  archShape.lineTo(0.90, cy + 0.052);
  archShape.lineTo(0.90, cy);
  archShape.closePath();

  const archGeom = new THREE.ExtrudeGeometry(archShape, {
    depth: 0.24,
    bevelEnabled: true,
    bevelThickness: 0.02,
    bevelSize: 0.018,
    bevelSegments: 5,
    curveSegments: 32
  });
  archGeom.translate(0, 0, -0.12);
  parts.push(archGeom);

  // 2. Symmetric Left & Right Raised Drawbridge Bascule Leaves + Side Abutments + Twin Diagonal Ties
  for (const side of [-1, 1]) {
    const s = (x) => side * x;

    // 2A. Main Raised Bascule Leaf (thick diagonal drawbridge ramp)
    // Matches reference silhouette: vertical inner top cut, flat peak, parallel diagonal deck, notched base foot
    const rampPts = [
      [s(0.19), 0.56],
      [s(0.37), 0.56],
      [s(1.18), -0.68],
      [s(1.06), -0.83],
      [s(0.84), -0.83],
      [s(0.19), 0.17]
    ];
    if (side === -1) rampPts.reverse();
    parts.push(createExtrudedPolygon(rampPts, 0.34, 0.026, 6, 0));

    // Subtle 3D side girder ribs on the bascule leaf for rich 3D depth when rotated
    const ribPts = [
      [s(0.24), 0.48],
      [s(0.33), 0.48],
      [s(1.08), -0.67],
      [s(0.92), -0.74],
      [s(0.24), 0.30]
    ];
    if (side === -1) ribPts.reverse();
    parts.push(createExtrudedPolygon(ribPts, 0.42, 0.018, 4, 0));

    // 2B. Outer Vertical Abutment Pillar (with bottom chamfer parallel to the ramp)
    const pierPts = [
      [s(1.02), 0.07],
      [s(1.18), 0.07],
      [s(1.18), -0.52],
      [s(1.02), -0.27]
    ];
    if (side === -1) pierPts.reverse();
    parts.push(createExtrudedPolygon(pierPts, 0.28, 0.02, 5, 0));

    // 2C. Inner Slender Vertical Abutment Strut (x ≈ 0.90..0.95)
    const strutPts = [
      [s(0.90), 0.14],
      [s(0.95), 0.14],
      [s(0.95), -0.18],
      [s(0.90), -0.10]
    ];
    if (side === -1) strutPts.reverse();
    parts.push(createExtrudedPolygon(strutPts, 0.22, 0.014, 4, 0));

    // 2D. Twin Parallel Diagonal Suspension Tie-Beams (connecting pier cap to upper drawbridge leaf)
    const tie1Pts = [
      [s(0.92), 0.14],
      [s(0.95), 0.10],
      [s(0.67), -0.08],
      [s(0.64), -0.03]
    ];
    const tie2Pts = [
      [s(0.92), 0.03],
      [s(0.95), -0.01],
      [s(0.73), -0.16],
      [s(0.70), -0.11]
    ];
    if (side === -1) {
      tie1Pts.reverse();
      tie2Pts.reverse();
    }
    // Placed as front & back 3D suspension pairs along Z
    for (const zOff of [-0.07, 0.07]) {
      parts.push(createExtrudedPolygon(tie1Pts, 0.06, 0.012, 4, zOff));
      parts.push(createExtrudedPolygon(tie2Pts, 0.06, 0.012, 4, zOff));
    }
  }

  // 3. Central Triple Vertical Spire between the Raised Drawbridge Leaves
  // 3A. Tall center needle reaching from bottom (-0.75) up to the arch apex (+0.85)
  const centerSpirePts = [
    [-0.022, 0.85],
    [0.022, 0.85],
    [0.022, -0.75],
    [-0.022, -0.75]
  ];
  parts.push(createExtrudedPolygon(centerSpirePts, 0.22, 0.014, 4, 0));

  // 3B. Two flanking shorter vertical rods at x = ±0.085 (from y = -0.75 to y = +0.16)
  for (const side of [-1, 1]) {
    const cx = side * 0.085;
    const sideRodPts = [
      [cx - 0.019, 0.16],
      [cx + 0.019, 0.16],
      [cx + 0.019, -0.75],
      [cx - 0.019, -0.75]
    ];
    parts.push(createExtrudedPolygon(sideRodPts, 0.18, 0.012, 4, 0));
  }

  return normalizeGlassGeometry(parts);
}
