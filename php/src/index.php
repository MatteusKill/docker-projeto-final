<?php
declare(strict_types=1);

$backendUrl = getenv('BACKEND_BASE_URL') ?: 'http://backend:8000';
$backendStatus = 'indisponível';
$context = stream_context_create([
    'http' => ['timeout' => 2, 'ignore_errors' => true],
]);
$response = @file_get_contents($backendUrl . '/health', false, $context);

if ($response !== false) {
    $health = json_decode($response, true);
    if (is_array($health) && ($health['status'] ?? '') === 'healthy') {
        $backendStatus = 'saudável';
    }
}
?>
<!doctype html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Projeto Final Docker</title>
    <style>
        body {
            max-width: 720px;
            margin: 60px auto;
            padding: 0 20px;
            font-family: system-ui, sans-serif;
            line-height: 1.6;
            background: #f4f6f8;
            color: #17202a;
        }
        main {
            padding: 32px;
            border: 1px solid #d5d8dc;
            border-radius: 12px;
            background: white;
        }
        button {
            padding: 10px 16px;
            border: 0;
            border-radius: 6px;
            background: #1769aa;
            color: white;
            cursor: pointer;
        }
        code { color: #1769aa; }
    </style>
</head>
<body>
<main>
    <h1>Projeto Final Docker</h1>
    <p>Esta página passa pelo Traefik e Nginx antes de chegar ao PHP-FPM.</p>
    <p>Backend FastAPI: <strong><?= htmlspecialchars($backendStatus, ENT_QUOTES, 'UTF-8') ?></strong></p>
    <p>Visitas registradas: <strong id="total">carregando...</strong></p>
    <button id="register" type="button">Registrar visita</button>
    <p id="message"></p>
    <p><a href="/api/docs">Documentação da API</a></p>
</main>
<script>
    const total = document.querySelector('#total');
    const message = document.querySelector('#message');
    const button = document.querySelector('#register');

    async function updateTotal() {
        const response = await fetch('/api/visits');
        if (!response.ok) throw new Error('Falha ao consultar visitas.');
        const data = await response.json();
        total.textContent = data.total;
    }

    button.addEventListener('click', async () => {
        button.disabled = true;
        try {
            const response = await fetch('/api/visits', { method: 'POST' });
            if (!response.ok) throw new Error('Falha ao registrar visita.');
            await updateTotal();
            message.textContent = 'Visita salva no MySQL e cache Redis invalidado.';
        } catch (error) {
            message.textContent = error.message;
        } finally {
            button.disabled = false;
        }
    });

    updateTotal().catch((error) => {
        total.textContent = 'indisponível';
        message.textContent = error.message;
    });
</script>
</body>
</html>
