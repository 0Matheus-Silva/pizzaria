# Bella Pizza

Aplicação Flask em português para catálogo, conta de cliente, carrinho, checkout, acompanhamento de pedidos e operação administrativa básica.

## Modelagem

O catálogo (`Category`, `Product`, `ProductSize`, `Addon` e `Promotion`) é independente do histórico de vendas. `Order` registra totais e endereço em snapshot; `OrderItem` e `OrderItemAddon` preservam nomes, tamanhos e preços praticados mesmo que o catálogo mude. `User` possui endereços próprios e pedidos; `Payment` e `OrderStatusHistory` mantêm o estado financeiro e operacional, enquanto `AuditLog` registra ações administrativas essenciais. Valores comerciais usam `Numeric(10, 2)`. As rotas de compra consultam preços, opções, promoções ativas e taxas no banco, sem confiar em preços enviados pelo navegador.

## Requisitos

- Python 3.12 ou superior compatível.
- MySQL 8 para desenvolvimento local/implantação; SQLite isolado nos testes.
- Dependências listadas em `requirements.txt`.

## MySQL local e inicialização automática

O projeto usa Flask-SQLAlchemy e Flask-Migrate (Alembic). As migrations versionadas em `migrations/versions/` definem as tabelas e relacionamentos. Ao executar `python run.py` fora de produção, o app verifica o MySQL, cria o banco se necessário, aplica migrations pendentes e valida o head e as tabelas antes de iniciar. Um lock MySQL serializa inicializações concorrentes; o servidor é iniciado sem recarregador para não repetir o bootstrap. Nenhuma operação de downgrade ou remoção de tabela é executada.

Em uma instalação nova, uma pessoa administradora deve provisionar uma vez as duas contas no MySQL Workbench. Use senhas fortes próprias e configure as mesmas em `.env`:

```sql
CREATE USER IF NOT EXISTS 'pizzaria_app'@'127.0.0.1'
  IDENTIFIED BY 'SUBSTITUA_POR_UMA_SENHA_FORTE';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
  ON pizzaria_picon.* TO 'pizzaria_app'@'127.0.0.1';

CREATE USER IF NOT EXISTS 'pizzaria_provisioner'@'127.0.0.1'
  IDENTIFIED BY 'OUTRA_SENHA_FORTE_DE_PROVISIONAMENTO';

GRANT CREATE ON *.* TO 'pizzaria_provisioner'@'127.0.0.1';
```

O provisionador tem somente o privilégio MySQL `CREATE`, necessário para criar um schema que ainda não existe; esse privilégio é global no MySQL, mas não permite ler os dados das tabelas. A conta `pizzaria_app` é usada para acesso normal e migrations. Se contas já existirem, confira as permissões antes de alterá-las. Não use `root` na aplicação nem guarde credenciais administrativas no projeto.

Copie `.env.example` para `.env`, defina um `SECRET_KEY` aleatório e configure `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USER` e `MYSQL_PASSWORD`. `MYSQL_PROVISION_USER` e `MYSQL_PROVISION_PASSWORD` só são necessários quando o schema ainda não existe. O projeto monta a URL `mysql+pymysql` com `utf8mb4`, escapando corretamente caracteres especiais na senha. `DATABASE_URL`, quando definida, tem precedência para a conexão da aplicação; o provisionador usa host e porta da URL e as duas variáveis próprias de provisionamento.

Se o MySQL estiver indisponível, a autenticação falhar, o schema tiver charset incompatível ou as permissões forem insuficientes, a inicialização termina com erro claro. Não há fallback para SQLite. O schema existente nunca tem seu charset alterado automaticamente.

Em produção, defina `APP_ENV=production`: o bootstrap automático é desabilitado e as migrations devem ser executadas pelo procedimento de implantação.

## Executar localmente

1. Crie e ative um ambiente virtual.
2. Instale as dependências com `pip install -r requirements.txt`.
3. Configure `.env` conforme a seção MySQL local.
4. Inicie o app; banco e tabelas serão preparados automaticamente no modo local:

   ```powershell
   python run.py
   ```

   Para adicionar catálogo demonstrativo, execute em outro terminal:

   ```powershell
   flask --app run.py seed-demo
   ```

5. Crie o primeiro administrador de forma interativa:

   ```powershell
   flask --app run.py create-admin
   ```

O comando solicita a senha sem imprimi-la nos logs. Não existe usuário administrativo com senha padrão. Em produção, configure `APP_ENV=production`, `DATABASE_URL` e `SECRET_KEY` diretamente no ambiente do processo; o app não carrega `.env`, recusa iniciar sem o segredo, força cookies Secure e não aplica migrations automaticamente. Habilite HTTPS.

## Testes e migrações

Execute `pytest`. Os testes usam SQLite isolado e verificam acesso administrativo, preço autoritativo do servidor, snapshots e bairros atendidos, além da idempotência das migrations.

As migrations já estão versionadas neste repositório. Em desenvolvimento, `python run.py` aplica as migrations pendentes. Em produção, use `flask --app run.py db upgrade` como etapa controlada; não execute `db init` nem gere uma migration inicial duplicada.

Revise cada nova migração gerada antes de aplicá-la. Não execute `db downgrade` ou apague dados comerciais sem um plano de backup.

## Limites desta primeira versão

Este projeto é uma base funcional e não substitui preparação para produção. O fluxo de recuperação de senha/e-mail, edição de perfil, upload de imagens, CRUD completo de categorias/adicionais/promoções/zonas/configurações, controle detalhado de perfis, filtros analíticos, revisão jurídica e integração real com pagamentos/notificações ainda precisam ser implementados antes de operar uma loja real. Os depoimentos não foram apresentados como avaliações reais e nenhum pagamento é aprovado automaticamente.

Defina dados reais de contato, bairros e taxas no banco antes de aceitar pedidos. A configuração Pix é somente informativa; não são gerados QR Codes ou comprovantes.
