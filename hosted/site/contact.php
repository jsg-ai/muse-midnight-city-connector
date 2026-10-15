<?php
// Contact form for midnight.hyperkind.net
// Messages are stored in a SQLite database outside the web root.
// The "also email it" delivery mode is a stub for now: the message is
// always stored, and flagged email_status='queued' for later wiring to a
// real mail transport. Nothing is emailed yet.

declare(strict_types=1);
session_set_cookie_params(['httponly' => true, 'samesite' => 'Lax', 'secure' => true]);
session_start();

const DB_PATH = '/var/lib/midnight-contact/messages.db';
const TOPICS  = ['General', 'Support', 'Security', 'Business'];
// Delivery is OUR config, never a visitor choice:
// 'inbox' = store only. 'email' = store + queue for email once a transport
// is wired (stub today: stored with email_status='queued_stub').
const DELIVERY_MODE = 'inbox';

function db(): PDO {
    $pdo = new PDO('sqlite:' . DB_PATH);
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    $pdo->exec("CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        name TEXT NOT NULL,
        email TEXT NOT NULL DEFAULT '',
        topic TEXT NOT NULL DEFAULT 'General',
        message TEXT NOT NULL,
        deliver_mode TEXT NOT NULL DEFAULT 'inbox',
        email_status TEXT NOT NULL DEFAULT 'not_applicable',
        ip_hash TEXT NOT NULL DEFAULT '',
        read_at TEXT
    )");
    return $pdo;
}

function h(string $s): string { return htmlspecialchars($s, ENT_QUOTES, 'UTF-8'); }

$sent  = isset($_GET['sent']);
$error = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $tokenOk = isset($_POST['csrf'], $_SESSION['csrf'])
        && hash_equals($_SESSION['csrf'], (string)$_POST['csrf']);
    // Honeypot: humans never see or fill the "website" field.
    $bot = !empty($_POST['website']);
    // Time trap: a real person needs a few seconds to write a message.
    $tooFast = !isset($_SESSION['form_ts']) || (time() - (int)$_SESSION['form_ts'] < 3);

    $name    = trim((string)($_POST['name'] ?? ''));
    $email   = trim((string)($_POST['email'] ?? ''));
    $topic   = (string)($_POST['topic'] ?? 'General');
    $message = trim((string)($_POST['message'] ?? ''));
    $mode    = DELIVERY_MODE;

    if (!$tokenOk) {
        $error = 'Session expired. Please try again.';
    } elseif ($bot || $tooFast) {
        // Quietly accept-and-drop suspected bot submissions.
        header('Location: /contact?sent=1');
        exit;
    } elseif ($name === '' || mb_strlen($name) > 120) {
        $error = 'Please add your name (up to 120 characters).';
    } elseif ($message === '' || mb_strlen($message) > 5000) {
        $error = 'Please write a message (up to 5000 characters).';
    } elseif ($email !== '' && !filter_var($email, FILTER_VALIDATE_EMAIL)) {
        $error = 'That email address does not look right. Leave it blank if you do not need a reply.';
    } elseif (!in_array($topic, TOPICS, true)) {
        $error = 'Please pick a topic.';
    } else {
        try {
            $pdo = db();
            $ipHash = hash('sha256', (string)($_SERVER['REMOTE_ADDR'] ?? ''));
            $recent = $pdo->prepare("SELECT COUNT(*) FROM messages WHERE ip_hash = :h AND ts > datetime('now','-10 minutes')");
            $recent->execute([':h' => $ipHash]);
            if ((int)$recent->fetchColumn() >= 5) {
                $error = 'Too many messages in a short window. Please wait a few minutes.';
            } else {
                $stmt = $pdo->prepare("INSERT INTO messages
                    (ts, name, email, topic, message, deliver_mode, email_status, ip_hash)
                    VALUES (datetime('now'), :n, :e, :t, :m, :d, :es, :h)");
                $stmt->execute([
                    ':n'  => $name,
                    ':e'  => $email,
                    ':t'  => $topic,
                    ':m'  => $message,
                    ':d'  => $mode,
                    // Email transport is a stub: queue, never send (yet).
                    ':es' => $mode === 'email' ? 'queued_stub' : 'not_applicable',
                    ':h'  => $ipHash,
                ]);
                header('Location: /contact?sent=1');
                exit;
            }
        } catch (Throwable $e) {
            $error = 'Something broke on our side. Please try again in a bit.';
        }
    }
}

$_SESSION['csrf']    = bin2hex(random_bytes(16));
$_SESSION['form_ts'] = time();
?>
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Contact - Midnight City Connector by HyperKind</title>
<link rel="stylesheet" href="/style.css"><link rel="icon" href="/icon.svg" type="image/svg+xml">
<style>
label{display:block;margin:16px 0 6px;font-weight:600}
input[type=text],input[type=email],select,textarea{width:100%;padding:10px;border-radius:8px;border:1px solid #262c52;background:#0d1024;color:#e8eaf6;font:inherit}
textarea{min-height:150px}
.hp{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}
.radio{font-weight:400;display:block;margin:6px 0}
button{margin-top:20px;background:#39d0e8;color:#0b0e1a;border:0;padding:12px 26px;border-radius:8px;font:inherit;font-weight:700;cursor:pointer}
.err{background:#3a1230;border:1px solid #e854a8;border-radius:8px;padding:12px 16px}
.ok{background:#123a2a;border:1px solid #39e8a8;border-radius:8px;padding:12px 16px}
</style></head><body><main>
<nav><a href="/">Home</a><a href="/apidocs/">API docs</a><a href="/support">Support</a><a href="/contact">Contact</a><a href="/privacy">Privacy</a><a href="/terms">Terms</a></nav>
<p class="tag">Contact</p><h1>Contact us</h1>

<?php if ($sent): ?>
<div class="ok">Thank you - your message is saved and we will read it here.
</div>
<?php else: ?>
<?php if ($error): ?><div class="err"><?= h($error) ?></div><?php endif; ?>
<p>We do not publish an email address (it would be spammed into oblivion).
Use this form instead. Messages are stored on our server and read by a human.</p>
<form method="post" action="/contact">
<input type="hidden" name="csrf" value="<?= h($_SESSION['csrf']) ?>">
<label for="f-name">Your name</label>
<input type="text" id="f-name" name="name" maxlength="120" required>
<label for="f-email">Email (only if you want a reply)</label>
<input type="email" id="f-email" name="email" maxlength="200" autocomplete="email">
<label for="f-topic">Topic</label>
<select id="f-topic" name="topic">
<?php foreach (TOPICS as $t): ?><option value="<?= h($t) ?>"><?= h($t) ?></option><?php endforeach; ?>
</select>
<label for="f-message">Message</label>
<textarea id="f-message" name="message" maxlength="5000" required></textarea>
<div class="hp" aria-hidden="true"><label>Leave this field empty<input type="text" name="website" tabindex="-1" autocomplete="off"></label></div>

<button type="submit">Send message</button>
</form>
<p class="dim">Never send a Midnight City token, wallet seed, or password through
this form - support will never need them.</p>
<?php endif; ?>
<footer><a href="/contact">Contact HyperKind</a>.<br>
This is a community-built connector for the public Midnight City API. It is not affiliated with or endorsed by the Midnight City team; a permission request to the team is in progress.</footer>
</main></body></html>
