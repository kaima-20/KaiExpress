import traceback

try:
    from packages import create_app
except Exception:
    traceback.print_exc()
    raise

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)