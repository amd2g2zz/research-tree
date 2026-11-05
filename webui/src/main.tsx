import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.scss";

const root = document.getElementById("root");
if (root === null) throw new Error("#root element missing from index.html");
createRoot(root).render(<App />);
