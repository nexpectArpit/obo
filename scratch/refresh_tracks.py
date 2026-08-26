import json
from pathlib import Path
import sys
sys.path.append('.')
from agent.skill_adapter import adapt_track_target_skills

def main():
    learned = json.loads(Path('data/learned_skills.json').read_text())
    tracks = ['cpp', 'arch', 'os', 'ds', 'dl', 'maths']
    for t in tracks:
        adapt_track_target_skills(t, [], learned, {}, lambda x: Path(f"tracks/{'1_cpp' if x=='cpp' else '2_computer_architecture_and_networking' if x=='arch' else '3_os' if x=='os' else '4_data_science' if x=='ds' else '5_dl' if x=='dl' else '6_maths'}.json"))

if __name__ == '__main__':
    main()
