import { initializeApp } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-app.js";
import { 
  getAuth, 
  signInWithEmailAndPassword, 
  createUserWithEmailAndPassword,
  GoogleAuthProvider,
  signInWithPopup,
  signOut,
  onAuthStateChanged
} from "https://www.gstatic.com/firebasejs/10.8.0/firebase-auth.js";

if (window.location.hostname === "0.0.0.0") {
  const url = new URL(window.location.href);
  url.hostname = "localhost";
  window.location.replace(url.toString());
}

// Fetch Firebase configuration dynamically from the backend
let firebaseConfig = {};
try {
  const xhr = new XMLHttpRequest();
  xhr.open("GET", "/api/config/firebase", false); // synchronous request
  xhr.send(null);
  if (xhr.status === 200) {
    firebaseConfig = JSON.parse(xhr.responseText);
  } else {
    console.error("Failed to load Firebase configuration: Status", xhr.status);
  }
} catch (err) {
  console.error("Failed to fetch Firebase configuration: ", err);
}

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const googleProvider = new GoogleAuthProvider();

export {
  auth,
  googleProvider,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signInWithPopup,
  signOut,
  onAuthStateChanged,
};
