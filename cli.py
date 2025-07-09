"""SREArena CLI client."""

import asyncio
import atexit
import shutil

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from srearena.conductor import Conductor, exit_cleanup_fault
from srearena.service.kubectl import KubeCtl
from srearena.service.telemetry.prometheus import Prometheus
from srearena.service.shell import Shell
from srearena.service.apps.registry import AppRegistry
from srearena.utils.sigint_aware_section import SigintAwareSection
from srearena.utils.dependency_check import dependency_check

WELCOME = """
# SREArena
- Type your commands or actions below.
- Use `exit` to quit the application.
- Use `start <problem_id>` to begin a new problem.
- Use `deploy <app_name>` to deploy an available app.
"""

TASK_MESSAGE = """{prob_desc}
You are provided with the following APIs to interact with the service:

{telemetry_apis}

You are also provided an API to a secure terminal to the service where you can run commands:

{shell_api}

Finally, you will submit your solution for this task using the following API:

{submit_api}

At each turn think step-by-step and respond with your action.
"""


class HumanAgent:
    def __init__(self, conductor):
        self.session = PromptSession()
        self.console = Console(force_terminal=True, color_system="auto")
        self.conductor = conductor
        self.apps = AppRegistry()
        self.session_purpose = None # "problem", "app"

        self.instantiate_completer_options()

        self.completer = WordCompleter(self.available_options, ignore_case=True, match_middle=True, sentence=True)

        self.cleanup_initiated = False

    def instantiate_completer_options(self):
        pids = self.conductor.problems.get_problem_ids()
        app_names = self.apps.get_app_names()

        self.available_options = []

        for pid in pids:
            self.available_options.append(f"start {pid}")
        
        for app_name in app_names:
            self.available_options.append(f"deploy {app_name}")

    def display_welcome_message(self):
        self.console.print(Markdown(WELCOME), justify="center")
        self.console.print()

    def display_context(self, problem_desc, apis):
        self.shell_api = self._filter_dict(apis, lambda k, _: "exec_shell" in k)
        self.submit_api = self._filter_dict(apis, lambda k, _: "submit" in k)
        self.telemetry_apis = self._filter_dict(apis, lambda k, _: "exec_shell" not in k and "submit" not in k)

        stringify_apis = lambda apis: "\n\n".join([f"{k}\n{v}" for k, v in apis.items()])

        self.task_message = TASK_MESSAGE.format(
            prob_desc=problem_desc,
            telemetry_apis=stringify_apis(self.telemetry_apis),
            shell_api=stringify_apis(self.shell_api),
            submit_api=stringify_apis(self.submit_api),
        )

        self.console.print(Markdown(self.task_message))

    def display_env_message(self, env_input):
        self.console.print(Panel(env_input, title="Environment", style="white on blue"))
        self.console.print()

    async def set_session_purpose(self):
        user_input = await self.get_user_input(completer=self.completer)

        if user_input.startswith("start"):
            try:
                _, problem_id = user_input.split(maxsplit=1)
            except ValueError:
                self.console.print("Invalid command. Please use `start <problem_id>`")

            self.conductor.problem_id = problem_id.strip()
            self.session_purpose = "problem"
        elif user_input.startswith("deploy"):
            try:
                _, app_name = user_input.split(maxsplit=1)
            except ValueError:
                self.console.print("Invalid command. Please user `deploy <app_name>`")

            self.app_name = app_name.strip()
            self.session_purpose = "app"
        else:
            self.console.print("Invalid command. Please use `start <problem_id>` or `deploy <app_name>`")

    async def get_action(self, env_input):
        self.display_env_message(env_input)
        user_input = await self.get_user_input()

        if user_input.strip().startswith("submit(") and self.session_purpose == "app":
            self.display_env_message(f"[❌] Action is not supported while in app mode")
            return None

        if not user_input.strip().startswith("submit("):
            try:
                output = Shell.exec(user_input.strip())
                self.display_env_message(output)
            except Exception as e:
                self.display_env_message(f"[❌] Shell command failed: {e}")
            return await self.get_action(env_input)

        return f"Action:```\n{user_input}\n```"

    async def get_user_input(self, completer=None):
        loop = asyncio.get_running_loop()
        style = Style.from_dict({"prompt": "ansigreen bold"})
        prompt_text = [("class:prompt", "SREArena> ")]

        with patch_stdout():
            try:
                with SigintAwareSection():
                    input = await loop.run_in_executor(
                        None,
                        lambda: self.session.prompt(prompt_text, style=style, completer=completer),
                    )

                    if input.lower() == "exit":
                        raise SystemExit

                    return input
            except (SystemExit, KeyboardInterrupt, EOFError):
                match self.session_purpose:
                    case "problem":
                        atexit.register(exit_cleanup_fault, conductor=self.conductor)
                    case "app":
                        atexit.register(self.cleanup_app)
                raise SystemExit from None

    async def deploy_app(self):
        dependency_check(["kubectl", "helm"])

        self.kubectl = KubeCtl()
        self.app = self.apps.get_app_instance(self.app_name)
        self.prometheus = Prometheus()

        try:
            with SigintAwareSection():
                print(f"[Session Start] App: {self.app_name}")

                print("Setting up metrics-server...")
                self.kubectl.exec_command(
                    "kubectl apply -f "
                    "https://github.com/kubernetes-sigs/metrics-server/"
                    "releases/latest/download/components.yaml"
                )
                self.kubectl.exec_command(
                    "kubectl -n kube-system patch deployment metrics-server "
                    "--type=json -p='["
                    '{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"},'
                    '{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-preferred-address-types=InternalIP"}'
                    "]'"
                )
                self.kubectl.wait_for_ready("kube-system")  # metrics-server is deployed in kube-system

                print("Setting up OpenEBS...")
                self.kubectl.exec_command("kubectl apply -f https://openebs.github.io/charts/openebs-operator.yaml")
                self.kubectl.exec_command(
                    "kubectl patch storageclass openebs-hostpath "
                    '-p \'{"metadata":{"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}\''
                )
                self.kubectl.wait_for_ready("openebs")
                print("OpenEBS setup completed.")

                self.prometheus.deploy()

                self.app.delete()
                self.app.deploy()
                self.app.start_workload()
        except KeyboardInterrupt:
            print("\nImmediately terminating and Cleaning up...")
            atexit.register(self.cleanup_app)
            raise SystemExit from None
        
        await self.interact_app()
        
    async def interact_app(self):
        try:
            while True:
                instr = "Please take the next action"
                action = await self.get_action(instr)
                if action:
                    self.sprint.agent(action)
        except Exception as e:
            atexit.register(self.cleanup_app)
            raise e
        
    def cleanup_app(self):
        if self.cleanup_initiated:
            return
    
        self.cleanup_initiated = True

        self.app.cleanup()
        self.prometheus.teardown()
        self.kubectl.exec_command("kubectl delete sc openebs-hostpath openebs-device --ignore-not-found")
        self.kubectl.exec_command("kubectl delete -f https://openebs.github.io/charts/openebs-operator.yaml")

    def _filter_dict(self, dictionary, filter_func):
        return {k: v for k, v in dictionary.items() if filter_func(k, v)}

async def main():
    conductor = Conductor()
    agent = HumanAgent(conductor)
    conductor.register_agent(agent, name="human")

    agent.display_welcome_message()
    await agent.set_session_purpose()

    match agent.session_purpose:
        case "problem":
            results = await conductor.start_problem()
            print(results)
        case "app":
            await agent.deploy_app()
        case _:
            pass

if __name__ == "__main__":
    asyncio.run(main())
