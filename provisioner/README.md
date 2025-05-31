# Cloudlab Provisioner

This is a tool to automatically provision clusters on cloudlab.

## Provisoner Credentials

The provisioner needs a set of credentials to access the cloudlab API.
So, the provisioner will need to be connected to a cloudlab account.
The provisioner will needs its own set of public and private keys to access the provisioned clusters and managing them.

### Getting CloudLab Credentials

1. Go to https://www.cloudlab.us/
2. Login with your cloudlab account
3. On the top right corner, click on your username, and then click on "Download Credentials"
4. This will take you to a page with a button to download the credentials. Click on it.
5. This will download a file called `cloudlab.pem`.

The `cloudlab.pem` contains the encrypted private key to your cloudlab account and ssl certificate. You need to decrypt it before using it.

### Install OpenSSL (if not already installed)

For Ubuntu/Debian:
```bash
sudo apt install openssl
```

For macOS:
```bash
brew install openssl
```

### Decrypting the CloudLab Credentials

```bash
openssl rsa -in cloudlab.pem -out cloudlab_decrypted.pem
```

When prompted for a password, enter your CloudLab account password (the same one you use to login to the CloudLab website).
This will create a new file `cloudlab_decrypted.pem` containing your decrypted private key.
The SSL certificate remains in the original `cloudlab.pem` file.

### Usage

Copy the `context.json.example` file and rename it to `context.json` and fill in the required fields.

```bash
cd cloudlab-provisioner
cp context.json.example context.json
```

Fill in the required fields in the `context.json` file.
Required fields are:

- `cert-path`: The path to the CloudLab certificate.
- `key-path`: The path to the decrypted CloudLab private key.
- `user-name`: Your CloudLab username.
- `user-pubkeypath`: The path to your CloudLab public key.
- `project`: Your CloudLab project name. Use lowercase to avoid Slice URN conflicts.

Use absolute paths.