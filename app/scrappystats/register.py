
from scrappystats.tools.register_commands import register_commands
from scrappystats.version import VERSION

def main():
    print(f"ScrappyStats version: {VERSION}")
    status, text = register_commands()
    if status == 200:
        print("✅ Commands successfully re-registered.")
    else:
        print("❌ Command registration failed.")

if __name__ == "__main__":
    main()
