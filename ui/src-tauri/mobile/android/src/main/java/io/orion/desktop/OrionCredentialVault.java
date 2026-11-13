package io.orion.desktop;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.AtomicFile;
import android.util.Base64;
import java.io.DataInputStream;
import java.io.File;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.Key;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Locale;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Stores each remote session under an app-owned Android Keystore key. */
public final class OrionCredentialVault {
    private static final String KEYSTORE = "AndroidKeyStore";
    private static final String KEY_ALIAS = "orion-native-sessions-v1";
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int NONCE_SIZE = 12;
    private static final int TAG_SIZE = 16;
    private static final int MAX_VALUE_SIZE = 2560;
    private static final int VERSION = 1;
    private static OrionCredentialVault instance;

    private final File directory;

    private OrionCredentialVault(File noBackupFiles) {
        directory = new File(noBackupFiles, "orion-sessions");
    }

    public static synchronized OrionCredentialVault forApp(Context context) {
        if (instance == null) {
            instance = new OrionCredentialVault(context.getApplicationContext().getNoBackupFilesDir());
        }
        return instance;
    }

    public synchronized byte[] get(String origin) throws IOException, GeneralSecurityException {
        byte[] scope = canonicalOrigin(origin).getBytes(StandardCharsets.UTF_8);
        AtomicFile file = credentialFile(scope);
        byte[] record;
        try {
            record = readRecord(file);
        } catch (FileNotFoundException missing) {
            if (file.getBaseFile().exists()) throw missing;
            return null;
        }
        SecretKey key = credentialKey(false);
        if (key == null) throw new GeneralSecurityException("Orion credential key is unavailable");
        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_SIZE * Byte.SIZE, record, 1, NONCE_SIZE));
        cipher.updateAAD(scope);
        return cipher.doFinal(record, 1 + NONCE_SIZE, record.length - 1 - NONCE_SIZE);
    }

    public synchronized void set(String origin, byte[] value) throws IOException, GeneralSecurityException {
        byte[] scope = canonicalOrigin(origin).getBytes(StandardCharsets.UTF_8);
        if (value.length == 0 || value.length > MAX_VALUE_SIZE) {
            throw new IllegalArgumentException("Invalid Orion credential length");
        }
        if (!directory.isDirectory() && !directory.mkdirs() && !directory.isDirectory()) {
            throw new IOException("Cannot create Orion credential directory");
        }
        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.ENCRYPT_MODE, credentialKey(true));
        cipher.updateAAD(scope);
        byte[] nonce = cipher.getIV();
        if (nonce.length != NONCE_SIZE) throw new GeneralSecurityException("Invalid Keystore nonce");
        byte[] ciphertext = cipher.doFinal(value);
        byte[] record = new byte[1 + NONCE_SIZE + ciphertext.length];
        record[0] = VERSION;
        System.arraycopy(nonce, 0, record, 1, nonce.length);
        System.arraycopy(ciphertext, 0, record, 1 + nonce.length, ciphertext.length);

        AtomicFile file = credentialFile(scope);
        FileOutputStream output = file.startWrite();
        try {
            output.write(record);
        } catch (IOException | RuntimeException error) {
            file.failWrite(output);
            throw error;
        }
        file.finishWrite(output);
        if (!Arrays.equals(record, readRecord(file))) throw new IOException("Orion credential write did not persist");
    }

    public synchronized void clear(String origin) throws IOException, GeneralSecurityException {
        AtomicFile file = credentialFile(canonicalOrigin(origin).getBytes(StandardCharsets.UTF_8));
        file.delete();
        try {
            readRecord(file);
        } catch (FileNotFoundException missing) {
            if (file.getBaseFile().exists()) throw missing;
            return;
        }
        throw new IOException("Orion credential removal failed");
    }

    private AtomicFile credentialFile(byte[] scope) throws GeneralSecurityException {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(scope);
        String name = Base64.encodeToString(digest, Base64.URL_SAFE | Base64.NO_PADDING | Base64.NO_WRAP);
        return new AtomicFile(new File(directory, name));
    }

    private static byte[] readRecord(AtomicFile file) throws IOException {
        try (DataInputStream input = new DataInputStream(file.openRead())) {
            int size = input.available();
            if (size <= 1 + NONCE_SIZE + TAG_SIZE || size > 1 + NONCE_SIZE + TAG_SIZE + MAX_VALUE_SIZE) {
                throw new IOException("Invalid stored Orion credential size");
            }
            byte[] record = new byte[size];
            input.readFully(record);
            if (record[0] != VERSION || input.read() != -1) throw new IOException("Invalid stored Orion credential");
            return record;
        }
    }

    private static SecretKey credentialKey(boolean create) throws IOException, GeneralSecurityException {
        KeyStore store = KeyStore.getInstance(KEYSTORE);
        store.load(null);
        Key existing = store.getKey(KEY_ALIAS, null);
        if (existing != null) {
            if (existing instanceof SecretKey) return (SecretKey) existing;
            throw new GeneralSecurityException("Invalid Orion credential key");
        }
        if (!create) return null;
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE);
        generator.init(new KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .setRandomizedEncryptionRequired(true)
            .build());
        return generator.generateKey();
    }

    static String canonicalOrigin(String origin) {
        if (origin == null || origin.length() > 300) {
            throw new IllegalArgumentException("Invalid Orion server origin");
        }
        URI url;
        try {
            url = URI.create(origin);
        } catch (IllegalArgumentException malformed) {
            throw new IllegalArgumentException("Invalid Orion server origin");
        }
        String scheme = url.getScheme();
        String host = url.getHost();
        int port = url.getPort();
        boolean loopback = "127.0.0.1".equals(host) || "[::1]".equals(host);
        boolean https = "https".equals(scheme);
        if (host == null || !(https || "http".equals(scheme) && loopback) || port == 0 || port > 65535
            || port == (https ? 443 : 80) || url.getUserInfo() != null || !url.getRawPath().isEmpty()
            || url.getRawQuery() != null || url.getRawFragment() != null) {
            throw new IllegalArgumentException("Invalid Orion server origin");
        }
        String canonical = scheme + "://" + host.toLowerCase(Locale.ROOT) + (port < 0 ? "" : ":" + port);
        if (!origin.equals(canonical)) throw new IllegalArgumentException("Invalid Orion server origin");
        return canonical;
    }
}
