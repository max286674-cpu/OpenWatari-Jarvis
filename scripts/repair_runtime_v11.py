"""Safe runtime consistency repair.

Restores known-good canonical files, applies exact small patches, and validates syntax. Re-running is
idempotent and cannot delete unrelated helpers.
"""
from __future__ import annotations
import ast, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CANONICAL_CONFIG="88d5c6d3c0a310dc74e04642142849ab630622b8"
CANONICAL_TOOLS="f3def13a623ed737a6128c32cba0776e2b222d9f"
CANONICAL_ROUTER="f3def13a623ed737a6128c32cba0776e2b222d9f"

def read(rel): return (ROOT/rel).read_text(encoding="utf-8")
def write_if_changed(rel,text):
    p=ROOT/rel; old=p.read_text(encoding="utf-8")
    if old==text:return False
    p.write_text(text,encoding="utf-8"); return True
def git_file(commit,rel):
    try:return subprocess.check_output(["git","show",f"{commit}:{rel}"],cwd=ROOT,text=True,encoding="utf-8")
    except Exception as e:raise RuntimeError(f"cannot restore canonical {rel}: {e}") from e

def restore_canonical_files():
    changed=False
    for rel,commit in (("src/jarvis/config.py",CANONICAL_CONFIG),("src/jarvis/brain/tools/__init__.py",CANONICAL_TOOLS),("src/jarvis/brain/intent_router.py",CANONICAL_ROUTER)):
        changed=write_if_changed(rel,git_file(commit,rel)) or changed
    return changed

def patch_agent():
    rel="src/jarvis/brain/agent.py";s=read(rel);original=s
    old='''_AFFIRM_RE = re.compile(\n    r"^\\s*(yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|please do|please go ahead|confirm|"\n    r"confirmed|affirmative|sounds good|go for it|proceed|send it|do that|that'?s right|"\n    r"correct|fine|absolutely|yes please|go|right)\\b",\n    re.IGNORECASE,\n)'''
    new='''_AFFIRM_RE = re.compile(\n    r"^\\s*(yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|please do|please go ahead|confirm|"\n    r"confirmed|affirmative|sounds good|go for it|proceed|send it|do that|that'?s right|"\n    r"correct|fine|absolutely|yes please|go|right|да|ага|угу|ок|окей|хорошо|конечно|"\n    r"подтверждаю|подтверждено|разрешаю|разрешено|делай|делайте|выполняй|выполняйте|"\n    r"выполни|выполнить|запускай|запускайте|устанавливай|устанавливайте|установи|"\n    r"установить|продолжай|продолжайте|можно|добро|верно|точно|давай|давай делай)\\b",\n    re.IGNORECASE,\n)'''
    if old in s:s=s.replace(old,new)
    if "_PURE_CHAT_RE = re.compile(" not in s:
        marker="def _is_pure_chat(text: str) -> bool:";pos=s.find(marker)
        if pos<0:raise RuntimeError("agent.py missing _PURE_CHAT_RE")
        s=s[:pos]+'''_PURE_CHAT_RE = re.compile(\n    r"^\\s*(привет|здравствуй|здрасьте|доброе утро|добрый день|добрый вечер|спасибо|пожалуйста|класс|"\n    r"отлично|понял|понятно|хорошо|ага|угу|да|нет|почему|зачем|hi|hey+|hello|thanks|thank you|"\n    r"good job|nice|great|cool|got it|okay|ok)[\\s,.!?]*(джарвис|jarvis|сэр|sir)?[\\s,.!?]*$",\n    re.IGNORECASE,\n)\n\n\n'''+s[pos:]
    for old,new in {'"Right away, sir.",':'"Сделаю, сэр.",','"On it, sir.",':'"Занимаюсь этим, сэр.",','"Of course, sir.",':'"Конечно, сэр.",','"Yes, sir.",':'"Да, сэр.",','"Certainly, sir.",':'"Разумеется, сэр.",','"One moment, sir.",':'"Одну секунду, сэр.",','"Checking your vault"':'"Проверяю хранилище"','"Reading that note"':'"Читаю заметку"','"Saving that to your vault"':'"Сохраняю в хранилище"','"Looking that up"':'"Проверяю информацию"','"Opening the page"':'"Открываю страницу"','"Opening a browser"':'"Открываю браузер"','"Checking your Telegram"':'"Проверяю Telegram"','"Reading that chat"':'"Читаю чат"','"Sending that"':'"Отправляю"','"Working on your files"':'"Работаю с файлами"','"Running that"':'"Выполняю"','"In the browser"':'"Работаю в браузере"','"Setting that reminder"':'"Устанавливаю напоминание"','"Pinging your phone"':'"Отправляю уведомление"','"Getting the time"':'"Уточняю время"','"Checking the weather"':'"Проверяю погоду"','"Checking your calendar"':'"Проверяю календарь"','"Adding that to your calendar"':'"Добавляю в календарь"','"Checking your email"':'"Проверяю почту"','"Sending that email"':'"Отправляю письмо"','"Noting that down"':'"Запоминаю"','"Let me recall"':'"Вспоминаю"'}.items():s=s.replace(old,new)
    ast.parse(s,filename=rel);return write_if_changed(rel,s) if s!=original else False

def patch_config():
    rel="src/jarvis/config.py";s=read(rel);original=s
    for old,new in [('understood_languages: str = "English"','understood_languages: str = "Russian,English"'),('reply_language: str = "English"','reply_language: str = "Russian"'),('wake_word_threshold: float = 0.5','wake_word_threshold: float = 0.32'),('hot_mic_after_wake: bool = False','hot_mic_after_wake: bool = True'),('wake_ack_phrase: str = "Yes, sir?|I\'m listening, sir.|Sir?|Go ahead, sir."','wake_ack_phrase: str = "Да, сэр.|Слушаю, сэр.|Да, сэр, я слушаю."')]:s=s.replace(old,new)
    if 'desktop_tools_enabled:' not in s:s=s.replace('    mic_gain: float = 1.0\n','    mic_gain: float = 1.0\n    desktop_tools_enabled: bool = True\n',1)
    if 'wake_word_custom_model_path:' not in s:s=s.replace('    porcupine_access_key: str | None = None','    porcupine_access_key: str | None = None\n    wake_word_custom_model_path: str = "models/ru_jarvis.tflite"',1)
    ast.parse(s,filename=rel);return write_if_changed(rel,s) if s!=original else False

def patch_tools_registry():
    rel="src/jarvis/brain/tools/__init__.py";s=read(rel);original=s
    if '    desktop,' not in s:s=s.replace('    documents,\n','    desktop,\n    documents,\n',1)
    if 'system, desktop, browser,' not in s:s=s.replace('system, browser,','system, desktop, browser,',1)
    if '"screen": [multimodal, desktop]' not in s:s=s.replace('"screen": [multimodal],','"screen": [multimodal, desktop],',1)
    ast.parse(s,filename=rel);return write_if_changed(rel,s) if s!=original else False

def patch_router():
    rel="src/jarvis/brain/intent_router.py";s=read(rel);original=s
    s=s.replace(r'закрой|закрыть|выключи|выключить|останови|остановить',r'закрой|закрыть|выключи|выключить|останови|остановить|заверши|завершить')
    s=s.replace(r'открой|открыть|запусти|запустить',r'открой|открыть|запусти|запустить|включи|включить')
    ast.parse(s,filename=rel);return write_if_changed(rel,s) if s!=original else False

def patch_wake():
    rel="src/jarvis/edge/wake_word.py";s=read(rel);original=s
    anchor='''    models: list[str] = []\n    pending: list[str] = []\n    for phrase in desired:'''
    replacement='''    models: list[str] = []\n    pending: list[str] = []\n    try:\n        from jarvis.config import settings\n        custom = Path(settings.wake_word_custom_model_path).expanduser()\n        if custom.exists() and custom.suffix.lower() in {".tflite", ".onnx"}:\n            return [str(custom.resolve())], []\n    except Exception:\n        pass\n    for phrase in desired:'''
    if anchor in s and 'custom = Path(settings.wake_word_custom_model_path)' not in s:s=s.replace('import asyncio\n','import asyncio\nfrom pathlib import Path\n',1).replace(anchor,replacement,1)
    s=s.replace('self._model = Model(wakeword_models=models, inference_framework="onnx")','framework = "tflite" if any(str(m).lower().endswith(".tflite") for m in models) else "onnx"\n        self._model = Model(wakeword_models=models, inference_framework=framework)')
    ast.parse(s,filename=rel);return write_if_changed(rel,s) if s!=original else False

def patch_policy():
    rel="src/jarvis/brain/proactive.py";s=read(rel);original=s
    old='''    if name == "process_op":\n        return (args or {}).get("action") in {"kill", "start"}'''
    new='''    if name == "process_op":\n        action = (args or {}).get("action")\n        target = str((args or {}).get("name") or (args or {}).get("command") or "").lower()\n        routine = ("telegram", "chrome", "msedge", "firefox", "discord", "spotify", "steam",\n                   "notepad", "calc", "calculator", "code", "winword", "excel", "powerpnt")\n        # Opening/closing ordinary desktop applications is routine local work and never asks for approval.\n        if action in {"start", "kill"} and any(x in target for x in routine):\n            return False\n        return action in {"kill", "start"}'''
    if old in s:s=s.replace(old,new)
    ast.parse(s,filename=rel);return write_if_changed(rel,s) if s!=original else False

def validate():
    checks={"src/jarvis/brain/agent.py":("_PURE_CHAT_RE = re.compile(","def _is_pure_chat(","def _is_affirmation(","def _execute_calls("),"src/jarvis/brain/intent_router.py":("def forced_tools(",),"src/jarvis/brain/tools/desktop.py":("desktop_action","desktop_screenshot"),"src/jarvis/edge/wake_word.py":("wake_word_custom_model_path","inference_framework=framework"),"src/jarvis/brain/proactive.py":("routine = (",)}
    for rel,needles in checks.items():
        s=read(rel)
        for n in needles:
            if n not in s:raise RuntimeError(f"runtime invariant missing: {rel}: {n}")
        ast.parse(s,filename=rel)

def main():
    changed=restore_canonical_files();changed=patch_agent() or changed;changed=patch_config() or changed;changed=patch_tools_registry() or changed;changed=patch_router() or changed;changed=patch_wake() or changed;changed=patch_policy() or changed;validate();print("runtime repair: OK (canonical restore + idempotent patches)"+("; files updated" if changed else "; already clean"))
if __name__=="__main__":main()
