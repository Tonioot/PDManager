from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from database import Base


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    repo_url = Column(String(500), nullable=False)
    github_token = Column(String(200), nullable=True)
    domain = Column(String(200), nullable=True)
    extra_domains = Column(Text, nullable=True)     # JSON list of additional domains/subdomains
    redirect_domains = Column(Text, nullable=True)  # JSON list of domains that redirect to primary
    ssl_cert_path = Column(String(500), nullable=True)
    ssl_key_path = Column(String(500), nullable=True)
    app_type = Column(String(50), nullable=True)
    start_command = Column(String(500), nullable=True)
    port = Column(Integer, nullable=True)
    status = Column(String(20), default="stopped")
    pid = Column(Integer, nullable=True)
    working_dir = Column(String(500), nullable=True)
    env_vars = Column(Text, nullable=True)
    nginx_enabled  = Column(Boolean, default=False)
    auto_start     = Column(Boolean, default=False)
    restart_policy = Column(String(20), default="no")   # no | always | on-failure
    maintenance_mode = Column(Boolean, default=False)
    update_mode      = Column(Boolean, default=False)
    downtime_page    = Column(Text, nullable=True)  # JSON: {title, message, color, custom_html}
    update_page      = Column(Text, nullable=True)  # JSON: {title, message, color, custom_html}
    restart_page     = Column(Text, nullable=True)  # JSON: {title, message, color, custom_html}
    starting_page    = Column(Text, nullable=True)  # JSON: {title, message, color, custom_html}
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
