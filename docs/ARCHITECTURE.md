# Customer360 Enterprise Lakehouse Architecture

## High-Level Architecture

                        Public Datasets
                              │
                              ▼
                    Batch & Streaming Ingestion
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
     Batch Loader                         Event Producer
          │                                       │
          └───────────────────┬───────────────────┘
                              ▼
                       Bronze Data Layer
                              │
                              ▼
                       Spark Transformations
                              │
                 Bronze → Silver → Gold
                              │
                              ▼
                    PostgreSQL Analytics
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
     FastAPI REST API                   Streamlit Dashboard
