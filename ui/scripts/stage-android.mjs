import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";

const generatedApp = new URL("../src-tauri/gen/android/app/", import.meta.url);
const source = new URL(
  "../src-tauri/mobile/android/src/main/java/io/orion/desktop/",
  import.meta.url,
);
const destination = new URL("src/main/java/io/orion/desktop/", generatedApp);
const gradleFile = new URL("build.gradle.kts", generatedApp);

let gradle;
try {
  gradle = await readFile(gradleFile, "utf8");
} catch (error) {
  if (error.code !== "ENOENT") throw error;
  throw new Error("Run npm exec -- tauri android init --ci before building Orion for Android.");
}

await mkdir(destination, { recursive: true });
for (const file of ["OrionCredentialVault.java", "OrionVaultPlugin.java", "OrionQrPlugin.java"]) {
  await copyFile(new URL(file, source), new URL(file, destination));
}

const scanner = 'implementation("com.journeyapps:zxing-android-embedded:4.3.0")';
if (!gradle.includes(scanner)) {
  const anchor = /^dependencies \{(\r?\n)/m;
  if (!anchor.test(gradle)) throw new Error("Generated Android app has no dependencies block.");
  await writeFile(gradleFile, gradle.replace(anchor, `dependencies {$1    ${scanner}$1`));
}
