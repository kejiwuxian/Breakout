/**
 * Three.js / WebGL sky map host. Geometry and HEALPix overlay come later.
 */
import * as THREE from "three";

export function mountSkyPlaceholder(container: HTMLElement): () => void {
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 100);
  camera.position.z = 2.5;

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.appendChild(renderer.domElement);

  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(1, 48, 32),
    new THREE.MeshBasicMaterial({
      color: 0x3dd6c6,
      wireframe: true,
      transparent: true,
      opacity: 0.35,
    }),
  );
  scene.add(mesh);

  const resize = () => {
    const w = container.clientWidth || 320;
    const h = container.clientHeight || 240;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);
  };
  resize();

  let frame = 0;
  const tick = () => {
    frame = requestAnimationFrame(tick);
    mesh.rotation.y += 0.003;
    renderer.render(scene, camera);
  };
  tick();

  window.addEventListener("resize", resize);
  return () => {
    cancelAnimationFrame(frame);
    window.removeEventListener("resize", resize);
    renderer.dispose();
    container.removeChild(renderer.domElement);
  };
}
