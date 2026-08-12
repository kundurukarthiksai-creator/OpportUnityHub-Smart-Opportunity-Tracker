import os
import base64
import secrets

def main():
    template_path = ".env.template"
    env_path = ".env"
    
    if not os.path.exists(template_path):
        print(f"Error: {template_path} not found!")
        return

    # Check if .env already exists
    if os.path.exists(env_path):
        confirm = input(".env file already exists. Overwrite with fresh keys? (y/N): ").strip().lower()
        if confirm != 'y':
            print("Aborted. No changes made to your existing .env file.")
            return

    # Generate secure secrets
    jwt_secret = secrets.token_hex(32)
    # Generate 32 bytes base64 urlsafe key
    encryption_key = base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8')

    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace placeholders
    content = content.replace("your-jwt-signing-secret-key-change-this-in-production", jwt_secret)
    content = content.replace("your-32-byte-base64-encoded-key-for-oauth-token-encryption", encryption_key)

    with open(env_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print("\n==============================================")
    print(" Successfully generated .env file!")
    print("==============================================")
    print("1. Generated secure random JWT_SECRET.")
    print("2. Generated secure random ENCRYPTION_KEY.")
    print("3. Copied template structure to .env.")
    print("\nNext steps:")
    print("Please open the '.env' file and fill in your Supabase, Google OAuth, and Gemini API keys.")
    print("Refer to SETUP_ENV.md for detailed instructions on how to get these keys.")
    print("==============================================\n")

if __name__ == "__main__":
    main()
