#!/usr/bin/env python3
"""
更新4个cron job的prompt，在邮件发送前插入浏览器核验检查。
"""
import json
import re
import subprocess
import sys

CRON_IDS = {
    "premarket-0900": "0d61fb36-42e7-48ec-bcd1-e5feb498666b",
    "call-auction-0925": "68fb4f6e-cea7-4e56-a2ce-ac317a1039de",
    "sector-flow-1000": "8c8599fc-a65d-45ba-a785-760514152203",
    "postmarket-1500": "52fd222b-3241-4118-8a48-1f44e1eae8cb",
}

VERIFY_BLOCK = """\
# 🔴 浏览器核验前置检查（不可跳过）
python3 /home/chris/.openclaw/workspace/skills/a-share-master/scripts/browser_verify_checker.py check
if [ $? -ne 0 ]; then
  echo "❌ 浏览器核验未通过，报告已阻止发送！"
  echo "请先完成以下核验步骤："
  python3 /home/chris/.openclaw/workspace/skills/a-share-master/scripts/browser_verify_checker.py status
  exit 1
fi"""

EMAIL_BLOCK_PATTERN = re.compile(
    r'(## 📧 发送邮件\n```bash\n).*?(?=\n```\n\n)',
    re.DOTALL
)


def extract_cat_cmd(bash_content):
    """Extract the cat REPORTEOF command from bash content"""
    m = re.search(r"(cat << '?REPORTEOF'?\s+.*?REPORTEOF)", bash_content, re.DOTALL)
    return m.group(1) if m else None


def replace_email_section(prompt):
    """Replace email sending section with verified version"""
    def _replacer(match):
        header = match.group(1)
        full_match = match.group(0)
        cat_cmd = extract_cat_cmd(full_match)
        if not cat_cmd:
            return full_match  # fallback: keep original
        return f"""\
## 📧 发送邮件
```bash
{VERIFY_BLOCK}

{cat_cmd}
```
"""
    return EMAIL_BLOCK_PATTERN.sub(_replacer, prompt)


def get_cron(cron_id):
    """Get cron job JSON data"""
    r = subprocess.run(
        ["openclaw", "cron", "get", cron_id],
        capture_output=True, text=True, timeout=30
    )
    out = r.stdout
    idx = out.find('{')
    if idx == -1:
        # Also check stderr
        out = r.stderr
        idx = out.find('{')
        if idx == -1:
            raise ValueError(f"No JSON found in output for {cron_id}")
    return json.loads(out[idx:])


def update_cron(cron_id, new_prompt):
    """Update cron job prompt"""
    r = subprocess.run(
        ["openclaw", "cron", "edit", cron_id, "--message", new_prompt],
        capture_output=True, text=True, timeout=30
    )
    if r.returncode != 0:
        print(f"  ❌ Update command failed: {r.stderr.strip()}")
        return False
    return True


def verify_update(prompt_before, prompt_after, name):
    """Verify the update was applied correctly"""
    issues = []
    
    if prompt_before == prompt_after:
        issues.append("Prompt unchanged (regex didn't match)")
    
    if "browser_verify_checker.py check" not in prompt_after:
        issues.append("Verify block missing after update")
    
    if "## 📧 发送邮件" not in prompt_after:
        issues.append("Email section header missing after update")
    
    # Verify the old email send command still exists
    if "email_report.py" not in prompt_after:
        issues.append("email_report command missing after update")
    
    # Check no stray backtick artifacts
    # Original cat command patterns
    orig_cat_count = prompt_before.count("cat << 'REPORTEOF'")
    new_cat_count = prompt_after.count("cat << 'REPORTEOF'")
    if orig_cat_count != new_cat_count:
        issues.append(f"Cat command count changed: {orig_cat_count} -> {new_cat_count}")
    
    return issues


def main():
    results = {}
    
    for name, cid in CRON_IDS.items():
        print(f"\n{'='*60}")
        print(f"📝 Processing: {name} ({cid})")
        
        try:
            data = get_cron(cid)
        except Exception as e:
            print(f"  ❌ Failed to get cron: {e}")
            results[name] = "get_failed"
            continue
        
        prompt = data.get("payload", {}).get("message", "")
        if not prompt:
            print(f"  ❌ No prompt/message field found!")
            results[name] = "no_prompt"
            continue
        
        orig_len = len(prompt)
        print(f"  📏 Original prompt: {orig_len} chars")
        
        new_prompt = replace_email_section(prompt)
        new_len = len(new_prompt)
        print(f"  📏 New prompt: {new_len} chars (+{new_len - orig_len})")
        
        issues = verify_update(prompt, new_prompt, name)
        if issues:
            print(f"  ❌ Verification failed:")
            for issue in issues:
                print(f"     - {issue}")
            results[name] = f"verify_failed: {'; '.join(issues)}"
            continue
        
        print(f"  ✅ Verification passed")
        
        success = update_cron(cid, new_prompt)
        if success:
            print(f"  ✅ {name}: Cron updated successfully!")
            results[name] = "updated"
        else:
            print(f"  ❌ {name}: Update failed")
            results[name] = "update_failed"
    
    # Summary
    print(f"\n{'='*60}")
    print(f"📊 SUMMARY")
    print(f"{'='*60}")
    for name, status in results.items():
        icon = "✅" if status == "updated" else "❌"
        print(f"  {icon} {name}: {status}")


if __name__ == "__main__":
    main()
