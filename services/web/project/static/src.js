
import * as THREE from 'three';


import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls';
import { BVHLoader } from 'three/examples/jsm/loaders/BVHLoader';

var clock = new THREE.Clock();

var camera, controls, scene, renderer;
var mixer, skeletonHelper;
var mixer1, skeletonHelper1;
const dataURL = document.getElementById("current-url").content
const originalURL = document.getElementById("original-url").content


init();
animate();


/*var loader1 = new BVHLoader();
loader1.load(originalURL, function ( result ) {

	skeletonHelper1 = new THREE.SkeletonHelper( result.skeleton.bones[ 0 ] );
	skeletonHelper1.skeleton = result.skeleton; // allow animation mixer to bind to THREE.SkeletonHelper directly
	skeletonHelper1.material.linewidth = 10

	var boneContainer = new THREE.Group();
	boneContainer.add( result.skeleton.bones[ 0 ] );

	scene.add( skeletonHelper1 );
	scene.add( boneContainer );

	// play animation
	mixer1 = new THREE.AnimationMixer( skeletonHelper1 );
	mixer1.clipAction( result.clip ).setEffectiveWeight( 1.0 ).play();
	if(mixer != null) mixer1.setTime(mixer.time)
} );*/

var loader = new BVHLoader();
loader.load(dataURL, function ( result ) {

	skeletonHelper = new THREE.SkeletonHelper( result.skeleton.bones[ 0 ] );
	skeletonHelper.skeleton = result.skeleton; // allow animation mixer to bind to THREE.SkeletonHelper directly

	var boneContainer = new THREE.Group();
	boneContainer.add( result.skeleton.bones[ 0 ] );

	scene.add( skeletonHelper );
	scene.add( boneContainer );

	// play animation
	mixer = new THREE.AnimationMixer( skeletonHelper );
	mixer.clipAction( result.clip ).setEffectiveWeight( 1.0 ).play();
	if(mixer1 != null) mixer.setTime(mixer1.time)

} );

function init() {

	camera = new THREE.PerspectiveCamera( 60, window.innerWidth / window.innerHeight, 1, 1000 );
	camera.position.set( 0, 200, 300 );
	var pos = localStorage.getItem('camera_position')
	var rot = localStorage.getItem('camera_rotation')
	if(pos!=null && rot != null) {
		pos = JSON.parse(pos)
		rot = JSON.parse(rot)
		camera.position.set(pos.x, pos.y, pos.z)
		camera.rotation.set(rot._x, rot._y, rot._z)
	}


	scene = new THREE.Scene();
	scene.background = new THREE.Color( 0xfefefe );

	scene.add( new THREE.GridHelper( 400, 10 ) );

	// renderer
	renderer = new THREE.WebGLRenderer( { antialias: true } );
	renderer.setPixelRatio( window.devicePixelRatio );
	renderer.setSize( window.innerWidth, window.innerHeight );
	document.body.appendChild( renderer.domElement );

	controls = new OrbitControls( camera, renderer.domElement );
	controls.enablePan = false
	controls.enableDamping = true;
	controls.dampingFactor = 0.05;

	controls.target.set(0, 7, 0)

	controls.minDistance = 10;
	controls.maxDistance = 100;

	controls.addEventListener('change', savePosition)

	window.addEventListener( 'resize', onWindowResize, false );
}

function savePosition() {
	localStorage.setItem('camera_position', JSON.stringify(camera.position))
	localStorage.setItem('camera_rotation', JSON.stringify(camera.rotation))
}

function onWindowResize() {

	camera.aspect = window.innerWidth / window.innerHeight;
	camera.updateProjectionMatrix();

	renderer.setSize( window.innerWidth, window.innerHeight );

}

function animate() {

	requestAnimationFrame( animate );

	var delta = clock.getDelta();

	if ( mixer ) mixer.update( delta );
	if (mixer1) mixer1.update(delta);

	renderer.render( scene, camera );

	controls.update()

}
