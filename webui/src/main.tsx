import "@xyflow/react/dist/style.css";
import "./styles.css";

import { createRoot } from "react-dom/client";

import { App } from "./App";
import { readInjected } from "./io";

const { architecture, catalog } = readInjected();
const container = document.getElementById("root");
if (container) {
  createRoot(container).render(<App initial={architecture} catalog={catalog} />);
}
