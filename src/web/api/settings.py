from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.web.database import get_db
from src.web.models import AppSettings
from src.config import Settings

router = APIRouter()


class SettingUpdate(BaseModel):
    value: str


class SettingResponse(BaseModel):
    key: str
    value: str
    description: str

    class Config:
        from_attributes = True


# 配置项描述
SETTING_DESCRIPTIONS = {
    "ai_base_url": "AI 模型 API 地址",
    "ai_api_key": "AI 模型 API Key",
    "ai_model": "AI 模型名称",
    "notify_telegram_bot_token": "Telegram Bot Token",
    "notify_telegram_chat_id": "Telegram Chat ID",
    "http_proxy": "HTTP 代理地址",
    "daily_report_cron": "日报调度 cron 表达式",
}

# 需要展示的配置项(按顺序)
SETTING_KEYS = list(SETTING_DESCRIPTIONS.keys())


def _get_env_defaults() -> dict[str, str]:
    """从 .env / 环境变量读取当前值作为默认"""
    s = Settings()
    return {
        "ai_base_url": s.ai_base_url,
        "ai_api_key": s.ai_api_key,
        "ai_model": s.ai_model,
        "notify_telegram_bot_token": s.notify_telegram_bot_token,
        "notify_telegram_chat_id": s.notify_telegram_chat_id,
        "http_proxy": s.http_proxy,
        "daily_report_cron": s.daily_report_cron,
    }


@router.get("", response_model=list[SettingResponse])
def list_settings(db: Session = Depends(get_db)):
    settings = db.query(AppSettings).all()
    existing_map = {s.key: s for s in settings}

    env_defaults = _get_env_defaults()

    for key in SETTING_KEYS:
        desc = SETTING_DESCRIPTIONS.get(key, "")
        env_val = env_defaults.get(key, "")

        if key not in existing_map:
            # 新建条目，用 .env 值
            s = AppSettings(key=key, value=env_val, description=desc)
            db.add(s)
            settings.append(s)
        else:
            s = existing_map[key]
            if not s.description:
                s.description = desc
    db.commit()

    # 按预定义顺序排列
    order = {k: i for i, k in enumerate(SETTING_KEYS)}
    settings.sort(key=lambda s: order.get(s.key, 999))

    return settings


@router.put("/{key}", response_model=SettingResponse)
def update_setting(key: str, update: SettingUpdate, db: Session = Depends(get_db)):
    setting = db.query(AppSettings).filter(AppSettings.key == key).first()
    if not setting:
        desc = SETTING_DESCRIPTIONS.get(key, "")
        setting = AppSettings(key=key, value=update.value, description=desc)
        db.add(setting)
    else:
        setting.value = update.value

    db.commit()
    db.refresh(setting)
    return setting
