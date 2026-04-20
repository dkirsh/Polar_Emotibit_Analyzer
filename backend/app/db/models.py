from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    sessions = relationship("Session", back_populates="project")

class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    session_uid = Column(String, unique=True, index=True)  # E.g., S204
    subject_id = Column(String, index=True)
    
    emotibit_csv_path = Column(String, nullable=True)
    polar_csv_path = Column(String, nullable=True)
    event_markers_csv_path = Column(String, nullable=True)
    
    sync_passed = Column(Integer, default=0) # 0 = false, 1 = true
    sync_metrics = Column(JSON, nullable=True) # stores drift, overlap data
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    project = relationship("Project", back_populates="sessions")
