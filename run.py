from app import create_app

app = create_app()

if __name__ == "__main__":
    if app.config["APP_ENV"] != "production":
        from app.mysql_startup import DatabaseStartupError, initialize_mysql_database

        try:
            revision = initialize_mysql_database(app)
        except DatabaseStartupError as error:
            raise SystemExit(f"Inicialização do banco falhou: {error}") from None
        print(f"MySQL pronto; migrations verificadas em {revision}.")
    app.run(use_reloader=False)
    
