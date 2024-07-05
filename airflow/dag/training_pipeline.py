from __future__ import annotations
import os
import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from textwrap import dedent
from src.DiamondPricePrediction.pipeline.training_pipeline import TrainingPipeline

training_pipeline = TrainingPipeline()

with DAG(
    "gemstone_training_pipeline",
    default_args={"retries": 2},
    description="It is my training pipeline",
    schedule_interval="@weekly",
    start_date=pendulum.datetime(2024, 2, 7, tz="UTC"),
    catchup=False,
    tags=["machine_learning", "classification", "gemstone"],
) as dag:

    dag.doc_md = __doc__

    def data_ingestion(**kwargs):
        ti = kwargs["ti"]
        train_data_path, test_data_path = training_pipeline.start_data_ingestion()
        ti.xcom_push("data_ingestion_artifact", {"training_data_path": train_data_path, "test_data_path": test_data_path})

    def data_transformation(**kwargs):
        ti = kwargs["ti"]
        data_ingestion_artifact = ti.xcom_pull(task_ids="data_ingestion", key="data_ingestion_artifact")
        train_arr, test_arr = training_pipeline.start_data_transformation(data_ingestion_artifact["training_data_path"])
        train_arr = train_arr.tolist()
        test_arr = test_arr.tolist()
        ti.xcom_push("data_transformation_artifact", {"train_arr": train_arr, "test_arr": test_arr})

    def model_trainer(**kwargs):
        import numpy as np
        ti = kwargs["ti"]
        data_transformation_artifact = ti.xcom_pull(task_ids="data_transformation", key="data_transformation_artifact")
        train_arr = np.array(data_transformation_artifact["train_arr"])
        test_arr = np.array(data_transformation_artifact["test_arr"])
        training_pipeline.start_model_training(test_arr, train_arr)

    def push_data_to_s3(**kwargs):
        bucket_name = os.getenv("BUCKET_NAME")
        artifact_folder = "/app/artifact"
        os.system(f"aws s3 sync {artifact_folder} s3://{bucket_name}/artifact")

    data_ingestion_task = PythonOperator(
        task_id="data_ingestion",
        python_callable=data_ingestion,
    )
    data_ingestion_task.doc_md = dedent(
        """\
        #### Ingestion task
        This task creates a train and test file.
        """
    )

    data_transform_task = PythonOperator(
        task_id="data_transformation",
        python_callable=data_transformation,
    )
    data_transform_task.doc_md = dedent(
        """\
        #### Transformation task
        This task performs the transformation.
        """
    )

    model_trainer_task = PythonOperator(
        task_id="model_trainer",
        python_callable=model_trainer,
    )
    model_trainer_task.doc_md = dedent(
        """\
        #### Training task
        This task performs the training.
        """
    )

    push_data_to_s3_task = PythonOperator(
        task_id="push_data_to_s3",
        python_callable=push_data_to_s3,
    )

    data_ingestion_task >> data_transform_task >> model_trainer_task >> push_data_to_s3_task
