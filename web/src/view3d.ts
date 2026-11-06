// 3D preview of the server-lofted mesh: hold, wall plate and screw countersinks.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { PreviewState } from "./state/preview";
import { tok } from "./theme";

export class View3D {
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(30, 1, 1, 5000);
  private controls: OrbitControls;
  private root = new THREE.Group();
  private hold: THREE.Mesh | null = null;
  private wall: THREE.Mesh | null = null;
  private screws = new THREE.Group();
  private holdMat = new THREE.MeshStandardMaterial({ roughness: 0.62, metalness: 0 });
  private staleMat = new THREE.MeshStandardMaterial({ roughness: 0.62, metalness: 0, transparent: true, opacity: 0.45 });
  private wallMat = new THREE.MeshStandardMaterial({ roughness: 0.9, transparent: true, opacity: 0.55, side: THREE.DoubleSide });
  private screwMat = new THREE.MeshStandardMaterial({ color: 0x222222, roughness: 0.6 });
  private fitted = false;
  hung = false;
  wallAngleDeg = 45;

  constructor(private canvas: HTMLCanvasElement) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    this.renderer.setPixelRatio(window.devicePixelRatio || 1);
    // Physically based intensities (three r155+): a low fill so the key light shapes the surface,
    // which is what the preview is for (reading scoops, lips and tips).
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x445055, 0.55));
    const key = new THREE.DirectionalLight(0xffffff, 2.6);
    key.position.set(-120, 200, 260);
    const rim = new THREE.DirectionalLight(0xffffff, 0.9);
    rim.position.set(200, -80, 120);
    this.scene.add(key, rim, this.root);
    this.root.add(this.screws);
    this.camera.position.set(-180, 160, 320);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.addEventListener("change", () => this.render());
    new ResizeObserver(() => this.resize()).observe(canvas.parentElement!);
    this.applyTheme();
    this.resize();
    const tick = () => {
      if (this.controls.update()) this.render();
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  applyTheme(): void {
    this.holdMat.color.set(tok("--accent") || "#c81d6e");
    this.staleMat.color.set(tok("--muted") || "#888888");
    this.wallMat.color.set(tok("--wall") || "#c39d63");
    this.render();
  }

  private resize(): void {
    const r = this.canvas.parentElement!.getBoundingClientRect();
    this.renderer.setSize(r.width, r.height, false);
    this.camera.aspect = r.width / Math.max(1, r.height);
    this.camera.updateProjectionMatrix();
    this.render();
  }

  render(): void {
    this.renderer.render(this.scene, this.camera);
  }

  /** Nothing to show (e.g. after a reset): remove everything and frame the next hold when it arrives. */
  clear(): void {
    this.removeGeometry();
    this.fitted = false;
  }

  private removeGeometry(): void {
    if (this.hold) {
      this.root.remove(this.hold);
      this.hold.geometry.dispose();
      this.hold = null;
    }
    if (this.wall) {
      this.root.remove(this.wall);
      this.wall.geometry.dispose();
      this.wall = null;
    }
    this.screws.children.forEach((m: THREE.Object3D) => (m as THREE.Mesh).geometry.dispose());
    this.screws.clear();
  }

  update(state: PreviewState, mounting: { hole_dia: number; countersink_dia: number }): void {
    if (!state.mesh || !state.data) {
      if (!state.stale) this.clear(); // an error keeps the last good hold (shown stale); "nothing yet" clears it
      this.render();
      return;
    }
    this.removeGeometry();

    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(state.mesh.positions, 3));
    geo.setIndex(new THREE.BufferAttribute(state.mesh.indices, 1));
    geo.computeVertexNormals();
    geo.computeBoundingBox();
    this.hold = new THREE.Mesh(geo, state.stale ? this.staleMat : this.holdMat);
    this.root.add(this.hold);

    const bb = geo.boundingBox!;
    const wall = new THREE.PlaneGeometry(bb.max.x - bb.min.x + 40, bb.max.y - bb.min.y + 40);
    this.wall = new THREE.Mesh(wall, this.wallMat);
    this.wall.position.set((bb.min.x + bb.max.x) / 2, (bb.min.y + bb.max.y) / 2, -0.3);
    this.root.add(this.wall);

    const holeR = mounting.hole_dia / 2, csR = mounting.countersink_dia / 2;
    for (const s of state.data.screws) {
      const cone = new THREE.Mesh(new THREE.CylinderGeometry(csR, holeR, csR - holeR, 28, 1, true), this.screwMat);
      cone.rotation.x = Math.PI / 2;
      cone.position.set(s.x, s.y, s.face_z - (csR - holeR) / 2 + 0.25);
      const hole = new THREE.Mesh(new THREE.CylinderGeometry(holeR, holeR, Math.max(s.face_z, 1), 20, 1, true), this.screwMat);
      hole.rotation.x = Math.PI / 2;
      hole.position.set(s.x, s.y, s.face_z / 2);
      this.screws.add(cone, hole);
    }
    if (!this.fitted) {
      this.fit();
      this.fitted = true;
    }
    this.render();
  }

  setHung(on: boolean, wallAngleDeg = this.wallAngleDeg): void {
    this.hung = on;
    this.wallAngleDeg = wallAngleDeg;
    // Overhang: rotating about x by +angle tips the wall normal (z) downward and the top toward the climber.
    this.root.rotation.x = on ? (wallAngleDeg * Math.PI) / 180 : 0;
    this.render();
  }

  fit(): void {
    if (!this.hold) return;
    const box = new THREE.Box3().setFromObject(this.hold);
    const c = box.getCenter(new THREE.Vector3()), s = box.getSize(new THREE.Vector3());
    const dist = Math.max(s.x, s.y) * 2.3 + 60;
    this.controls.target.copy(c);
    this.camera.position.copy(c).add(new THREE.Vector3(-0.45, 0.42, 0.8).normalize().multiplyScalar(dist));
    this.controls.update();
    this.render();
  }
}
