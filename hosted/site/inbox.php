<?php
// Admin inbox for contact-form messages. Sits behind nginx basic auth.
// Read-only except "mark read". No reply-by-email yet (stub on the form side).
declare(strict_types=1);
const DB_PATH = '/var/lib/midnight-contact/messages.db';
function h(?string $s): string { return htmlspecialchars($s ?? '', ENT_QUOTES, 'UTF-8'); }

$pdo = new PDO('sqlite:' . DB_PATH);
$pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['mark_read'])) {
    $stmt = $pdo->prepare("UPDATE messages SET read_at = datetime('now') WHERE id = :id");
    $stmt->execute([':id' => (int)$_POST['mark_read']]);
    header('Location: /contact/inbox');
    exit;
}
$rows = $pdo->query("SELECT * FROM messages ORDER BY read_at IS NOT NULL, id DESC LIMIT 200")
            ->fetchAll(PDO::FETCH_ASSOC);
?>
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Contact inbox - midnight.hyperkind.net</title>
<link rel="stylesheet" href="/style.css">
<style>.msg{background:#141830;border:1px solid #262c52;border-radius:12px;padding:14px 18px;margin:14px 0}
.msg.read{opacity:.55}.meta{color:#9aa3c7;font-size:.85rem}button{background:#39d0e8;border:0;border-radius:6px;padding:5px 12px;font-weight:700;cursor:pointer}</style>
</head><body><main>
<h1>Contact inbox</h1>
<p class="meta"><?= count($rows) ?> most recent messages. Unread first.</p>
<?php if (!$rows): ?><p>No messages yet.</p><?php endif; ?>
<?php foreach ($rows as $r): ?>
<div class="msg<?= $r['read_at'] ? ' read' : '' ?>">
<div class="meta">#<?= (int)$r['id'] ?> - <?= h($r['ts']) ?> UTC - <?= h($r['topic']) ?>
 - deliver: <?= h($r['deliver_mode']) ?> - email: <?= h($r['email_status']) ?>
<?= $r['read_at'] ? ' - read ' . h($r['read_at']) : ' - UNREAD' ?></div>
<p><strong><?= h($r['name']) ?></strong><?php if ($r['email']): ?> (<?= h($r['email']) ?>)<?php endif; ?></p>
<p style="white-space:pre-wrap"><?= h($r['message']) ?></p>
<?php if (!$r['read_at']): ?>
<form method="post"><button name="mark_read" value="<?= (int)$r['id'] ?>">Mark read</button></form>
<?php endif; ?>
</div>
<?php endforeach; ?>
</main></body></html>
