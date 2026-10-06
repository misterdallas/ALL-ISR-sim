from .server import PORT, serve


def main():
    server = serve(PORT)
    print(f"ALL-ISR feed bench http://127.0.0.1:{server.server_address[1]}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
