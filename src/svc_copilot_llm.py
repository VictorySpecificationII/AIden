from fastapi import HTTPException
from langchain_community.llms import LlamaCpp
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from huggingface_hub import hf_hub_download
import os
import json
import threading
from lib_copilot_telemetry import OpenTelemetryInstrumentor

class LLMService:
    def __init__(self):
        # Initialize the OpenTelemetryInstrumentor
        instrumentor = OpenTelemetryInstrumentor(svc_name="llm_service", instance_id="instance-00")

        # Get the logger and tracer
        self.logger = instrumentor.get_logger(logging_area="llm_service")
        self.tracer = instrumentor.get_tracer()

        self.model_paths = {"mistral": None, "llama2": None}
        self.current_model_name = None
        self.llm = None
        self.llm_chain = None
        self.model_paths_file = "model_paths.json"
        self.lock = threading.Lock()
        
        self.load_model_paths()

    def load_model_paths(self):
        if os.path.exists(self.model_paths_file):
            with open(self.model_paths_file, "r") as file:
                self.model_paths = json.load(file)

    def save_model_paths(self):
        with open(self.model_paths_file, "w") as file:
            json.dump(self.model_paths, file)

    def download_models(self):
        with self.tracer.start_as_current_span("download_models") as span, self.lock:
            try:
                # Download Mistral model
                mistral_model_name = "TheBloke/Mistral-7B-OpenOrca-GGUF"
                mistral_model_file = "mistral-7b-openorca.Q4_K_M.gguf"
                self.model_paths["mistral"] = hf_hub_download(mistral_model_name, filename=mistral_model_file)

                # Download Llama-2 model
                llama2_model_name = "TheBloke/Llama-2-7B-Chat-GGUF"
                llama2_model_file = "llama-2-7b-chat.Q4_0.gguf"
                self.model_paths["llama2"] = hf_hub_download(llama2_model_name, filename=llama2_model_file)

                # Save model paths to file
                self.save_model_paths()

                self.logger.info("LLM models downloaded.")
                self.tracer.set_span_status(span, success=True)
                return {"model_paths": self.model_paths}
            except Exception as e:
                self.logger.error(f"Error downloading models: {str(e)}")
                self.tracer.set_span_status(span, success=False, message=str(e))
                raise HTTPException(status_code=500, detail=str(e))

    def load_llm(self, model_name: str):
        with self.tracer.start_as_current_span("load_llm") as span, self.lock:
            try:
                if model_name not in self.model_paths:
                    raise ValueError("Invalid model name. Use 'mistral' or 'llama2'.")

                model_path = self.model_paths.get(model_name)
                if model_path is None:
                    raise FileNotFoundError("Model not downloaded. Call /download-model first.")

                self.current_model_name = model_name
                self.logger.info(f"Model {model_name} loaded successfully with path {model_path}.")
                self.tracer.set_span_status(span, success=True)
                return model_path
            except Exception as e:
                self.logger.error(f"Error loading model {model_name}: {str(e)}")
                self.tracer.set_span_status(span, success=False, message=str(e))
                raise HTTPException(status_code=500, detail=str(e))

    def switch_model(self, model_name: str):
        with self.tracer.start_as_current_span("switch_model") as span, self.lock:
            try:
                model_path = self.model_paths.get(model_name)
                if model_path is None or not os.path.exists(model_path):
                    raise FileNotFoundError("Model not downloaded. Call /download-model first.")
                
                self.llm = LlamaCpp(
                    model_path=model_path,
                    n_gpu_layers=0,
                    n_batch=512,
                    verbose=False,
                )
                self.llm_chain = None
                self.current_model_name = model_name
                self.logger.info(f"Switched to model {model_name}.")
                self.tracer.set_span_status(span, success=True)
                return {"status": f"Switched to model {model_name}", "model_path": model_path}
            except Exception as e:
                self.logger.error(f"Error switching to model {model_name}: {str(e)}")
                self.tracer.set_span_status(span, success=False, message=str(e))
                raise HTTPException(status_code=500, detail=str(e))

    def instantiate_llm(self):
        with self.tracer.start_as_current_span("instantiate_llm") as span, self.lock:
            try:
                if self.current_model_name is None:
                    raise HTTPException(status_code=400, detail="No model loaded. Call /load-llm first.")
                
                model_path = self.model_paths.get(self.current_model_name)
                if model_path is None:
                    raise HTTPException(status_code=404, detail="Model path not found. Call /load-llm first.")
                
                self.llm = LlamaCpp(
                    model_path=model_path,
                    n_gpu_layers=0,
                    n_batch=512,
                    verbose=False,
                )
                self.logger.info("LLM instantiated.")
                self.tracer.set_span_status(span, success=True)
                return {"status": "LLM instantiated"}
            except Exception as e:
                self.logger.error(f"Error instantiating LLM: {str(e)}")
                self.tracer.set_span_status(span, success=False, message=str(e))
                raise HTTPException(status_code=500, detail=str(e))

    def create_llm_chain(self):
        with self.tracer.start_as_current_span("create_llm_chain") as span, self.lock:
            try:
                if self.llm is None:
                    raise HTTPException(status_code=400, detail="LLM not instantiated. Call /instantiate-llm first.")
                
                template = """
                You are AIden, a co-pilot and digital companion. You are witty, gentlemanly, and inquisitive with an engineering-oriented mindset. Please reflect these qualities in your response.

                Question: {question}

                Answer:
                """
                prompt = PromptTemplate(template=template, input_variables=["question"])
                self.llm_chain = LLMChain(prompt=prompt, llm=self.llm)
                self.logger.info("LLMChain created.")
                self.tracer.set_span_status(span, success=True)
                return {"status": "LLMChain created"}
            except Exception as e:
                self.logger.error(f"Error creating LLMChain: {str(e)}")
                self.tracer.set_span_status(span, success=False, message=str(e))
                raise HTTPException(status_code=500, detail=str(e))

    def ask_question(self, question: str):
        with self.tracer.start_as_current_span("ask_question") as span, self.lock:
            try:
                if self.llm_chain is None:
                    raise HTTPException(status_code=400, detail="LLMChain not created. Call /create-llm-chain first.")
                
                answer = self.llm_chain.run(question)
                self.logger.info("Query successful. Returning answer from LLM.")
                self.tracer.set_span_status(span, success=True)
                return answer
            except Exception as e:
                self.logger.error(f"Error during LLM query: {str(e)}")
                self.tracer.set_span_status(span, success=False, message=str(e))
                raise HTTPException(status_code=500, detail=str(e))

    def get_current_model_in_memory(self):
        with self.tracer.start_as_current_span("get_current_model_in_memory") as span, self.lock:
            try:
                if self.current_model_name:
                    self.logger.info(f"Current model in memory: {self.current_model_name}")
                    self.tracer.set_span_status(span, success=True)
                    return {"model": self.current_model_name, "status": "loaded"}
                else:
                    raise HTTPException(status_code=400, detail="No LLM model currently in memory. Call /load-llm first.")
            except Exception as e:
                self.logger.error(f"Error getting current model in memory: {str(e)}")
                self.tracer.set_span_status(span, success=False, message=str(e))
                raise HTTPException(status_code=500, detail=str(e))
