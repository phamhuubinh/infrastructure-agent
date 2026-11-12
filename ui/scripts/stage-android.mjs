import { access, copyFile, mkdir } from "node:fs/promises";

const generatedApp = new URL("../src-tauri/gen/android/app/", import.meta.url);
const source = new URL(
  "../src-tauri/mobile/android/src/main/java/io/orion/desktop/",
  import.meta.url,
);
const destination = new URL("src/main/java/io/orion/desktop/", generatedApp);

try {
  await access(new URL("build.gradle.kts", generatedApp));
} catch (error) {
  if (error.code !== "ENOENT") throw error;
  throw new Error("Run npm exec -- tauri android init --ci before building Orion for Android.");
}

await mkdir(destination, { recursive: true });
for (const file of ["OrionCredentialVault.java", "OrionVaultPlugin.java"]) {
  await copyFile(new URL(file, source), new URL(file, destination));
}
