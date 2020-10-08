
import * as THREE from 'three';


import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls';
import { BVHLoader } from 'three/examples/jsm/loaders/BVHLoader';

var clock = new THREE.Clock();

var camera, controls, scene, renderer;
var mixer, skeletonHelper;

const dataURL = document.getElementById("current-url").content


init();
animate();


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

} );

function init() {

	camera = new THREE.PerspectiveCamera( 60, window.innerWidth / window.innerHeight, 1, 1000 );
	camera.position.set( 0, 200, 300 );

	scene = new THREE.Scene();
	scene.background = new THREE.Color( 0xeeeeee );

	scene.add( new THREE.GridHelper( 400, 10 ) );

	// renderer
	renderer = new THREE.WebGLRenderer( { antialias: true } );
	renderer.setPixelRatio( window.devicePixelRatio );
	renderer.setSize( window.innerWidth, window.innerHeight );
	document.body.appendChild( renderer.domElement );

	controls = new OrbitControls( camera, renderer.domElement );
	controls.minDistance = 100;
	controls.maxDistance = 700;

	window.addEventListener( 'resize', onWindowResize, false );

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

	renderer.render( scene, camera );

}
