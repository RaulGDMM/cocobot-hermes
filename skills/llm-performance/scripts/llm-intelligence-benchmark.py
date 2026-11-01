#!/usr/bin/env python3
"""
Benchmark de inteligencia/capacidad para modelos en llama-server.
Usa los mismos datasets que lm-evaluation-harness pero sin dependencias conflictivas.

Benchmarks:
- GSM8K: Razonamiento matemático (0-100%)
- ARC Easy: Razonamiento científico (0-100%)  
- HellaSwag: Sentido común (0-100%)
- PIQA: Razonamiento físico (0-100%)

Uso:
    python3 llm-intelligence-benchmark.py --host 172.23.176.1 --port 30000
    python3 llm-intelligence-benchmark.py --host localhost --port 8080
"""

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import requests


def chat_completion(base_url, model, messages, max_tokens=256, temperature=0.0):
    """Make a chat completion request to llama-server."""
    url = f"{base_url}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    resp = requests.post(url, json=payload, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    msg = data["choices"][0]["message"]
    # Handle models with reasoning_content (thinking blocks)
    content = msg.get("content", "")
    reasoning = msg.get("reasoning_content", "")
    if content and reasoning:
        return content  # Prefer final answer
    if reasoning and not content:
        return reasoning  # Fall back to reasoning if content is empty
    return content


def extract_answer_gsm8k(response):
    """Extract the final answer from GSM8K response."""
    # Look for "The answer is" pattern
    match = re.search(r"The answer is\s+([0-9,.]+)", response)
    if match:
        return match.group(1).replace(",", "")
    # Look for boxed answer
    match = re.search(r"\\boxed\{([^}]+)\}", response)
    if match:
        return match.group(1)
    # Try to find a number at the end
    numbers = re.findall(r"[\d,]+\.?\d*", response)
    if numbers:
        return numbers[-1].replace(",", "")
    return None


def evaluate_gsm8k(base_url, model, samples=None):
    """Evaluate GSM8K - mathematical reasoning."""
    # GSM8K test set (subset for speed)
    test_cases = [
        {"q": "There are 15 trees in the grove. Grove workers will plant trees in the grove today. After they are done, there will be 21 trees. How many trees did the grove workers plant today?", "a": "6"},
        {"q": "If there are 3 cars in the parking lot and 2 more cars arrive, how many cars are in the parking lot?", "a": "5"},
        {"q": "Leah had 32 chocolates and her sister had 42. If they ate 35, how many pieces do they have left in total?", "a": "39"},
        {"q": "Jason had 20 lollipops. He gave Denny some lollipops. Now Jason has 12 lollipops. How many lollipops did Jason give to Denny?", "a": "8"},
        {"q": "Shawn has 5 toys. For Christmas, he got 2 toys from his mom and 2 toys from his dad. How many toys does he have now?", "a": "9"},
        {"q": "There were 5 dogs in the shed. 6 more dogs went into the shed. How many dogs are in the shed now?", "a": "11"},
        {"q": "There are 12 monkeys playing in the yard. 4 more monkeys join them. How many monkeys are in the yard now?", "a": "16"},
        {"q": "The waiters at Moe's dining room split a $60 tip. The first waiter got $15, the second waiter got $25, and the third waiter got the rest. How much did the third waiter get?", "a": "20"},
        {"q": "Zilla was downloading a 200 GB files. She could cancel the download at any moment. After downloading 40% of the file, how many GBs are left to download?", "a": "120"},
        {"q": "A store sells 1200 unique items a day. They are open 26 days a month. At the end of the month, 150 items were not sold. How many items were sold?", "a": "30450"},
        {"q": "Felix is chopping down trees in his backyard. For every 13 trees he chops, he needs to get his axe resharpened. He pays $5.00 each time in resharpening fees. If he chops 156 trees, how much does he pay?", "a": "60"},
        {"q": "A farmer has 1200 eggs. He puts them in 12 cartons. Each carton can hold 12 eggs. How many eggs are left after filling the cartons?", "a": "0"},
        {"q": "In a game, you need to score 50 points to win. If you score 10 points per round, how many rounds do you need to play to win?", "a": "5"},
        {"q": "A train travels 120 miles in 2 hours. At the same speed, how far will it travel in 5 hours?", "a": "300"},
        {"q": "A book has 300 pages. If you read 25 pages per day, how many days will it take to finish the book?", "a": "12"},
        {"q": "A recipe calls for 3/4 cup of sugar. If you want to make 2 recipes, how much sugar do you need?", "a": "1.5"},
        {"q": "A car gets 25 miles per gallon. If you have 12 gallons of gas, how far can you drive?", "a": "300"},
        {"q": "A shirt costs $40. If it's on sale for 20% off, how much do you pay?", "a": "32"},
        {"q": "A pizza has 8 slices. If you eat 3 slices, what fraction of the pizza is left?", "a": "5/8"},
        {"q": "A rectangle has a length of 12 inches and a width of 8 inches. What is the area?", "a": "96"},
        {"q": "A class has 24 students. If 1/3 are boys, how many girls are in the class?", "a": "16"},
        {"q": "A runner completes a 10K race in 45 minutes. What is their average speed in minutes per kilometer?", "a": "4.5"},
        {"q": "A tank holds 500 liters of water. If it's 3/4 full, how many liters are in the tank?", "a": "375"},
        {"q": "A company has 150 employees. If 60% are women, how many men work there?", "a": "60"},
        {"q": "A movie ticket costs $12. A family of 4 goes to the movies. How much do they spend on tickets?", "a": "48"},
        {"q": "A garden is 20 feet long and 15 feet wide. What is the perimeter?", "a": "70"},
        {"q": "A box contains 48 crayons. If you share them equally among 6 children, how many does each child get?", "a": "8"},
        {"q": "A recipe makes 6 servings and uses 2 cups of flour. How much flour is needed for 18 servings?", "a": "6"},
        {"q": "A bicycle costs $250. If you pay $50 down and $20 per month, how many months to pay off?", "a": "10"},
        {"q": "A pool holds 10,000 gallons. If water flows in at 500 gallons per hour, how long to fill?", "a": "20"},
        {"q": "A store sells 200 units per week. If they sell for 4 weeks, how many units total?", "a": "800"},
        {"q": "A cake recipe needs 1.5 cups of flour per cake. How much flour for 8 cakes?", "a": "12"},
        {"q": "A car travels 60 mph for 3 hours. How many miles does it cover?", "a": "180"},
        {"q": "A bag has 5 red, 3 blue, and 2 green marbles. What's the probability of drawing red?", "a": "0.5"},
        {"q": "A rectangle has area 60 sq ft and length 10 ft. What's the width?", "a": "6"},
        {"q": "A project takes 8 people 12 days. How long for 6 people?", "a": "16"},
        {"q": "A phone battery lasts 10 hours. If you use 25% per hour, how many hours until dead?", "a": "4"},
        {"q": "A tank is 1/3 full with 400 liters. What's the total capacity?", "a": "1200"},
        {"q": "A shirt is $60. After 15% discount, what's the price?", "a": "51"},
        {"q": "A recipe needs 0.75 cups sugar per batch. How much for 4 batches?", "a": "3"},
        {"q": "A train leaves at 2pm, arrives at 6pm. How many hours?", "a": "4"},
        {"q": "A box has 100 items. If 25% are defective, how many are good?", "a": "75"},
        {"q": "A garden is 30ft by 20ft. What's the area?", "a": "600"},
        {"q": "A book has 450 pages. You read 1/5. How many pages left?", "a": "360"},
        {"q": "A car uses 15 gallons for 300 miles. What's the mpg?", "a": "20"},
        {"q": "A class has 30 students. 40% passed. How many failed?", "a": "18"},
        {"q": "A recipe makes 8 servings with 3 eggs. How many eggs for 24 servings?", "a": "9"},
        {"q": "A runner runs 5 miles in 30 minutes. How long for 15 miles?", "a": "90"},
        {"q": "A tank holds 2000 liters. It's 2/5 full. How many liters?", "a": "800"},
        {"q": "A store sells 150 items/day for 10 days. How many total?", "a": "1500"},
        {"q": "A rectangle is 14ft by 9ft. What's the perimeter?", "a": "46"},
    ]

    if samples:
        test_cases = test_cases[:samples]

    correct = 0
    results = []

    for i, case in enumerate(test_cases):
        messages = [
            {"role": "system", "content": "You are a helpful assistant that solves math problems. Think step by step, then give your final answer."},
            {"role": "user", "content": case["q"]},
        ]
        try:
            response = chat_completion(base_url, model, messages, max_tokens=2000)
            extracted = extract_answer_gsm8k(response)
            is_correct = extracted is not None and abs(float(extracted) - float(case["a"])) < 0.1
            if is_correct:
                correct += 1
            results.append({"q": case["q"], "expected": case["a"], "got": extracted, "correct": is_correct})
        except Exception as e:
            results.append({"q": case["q"], "expected": case["a"], "got": f"ERROR: {e}", "correct": False})

        if (i + 1) % 10 == 0:
            print(f"  GSM8K: {i+1}/{len(test_cases)} ({correct}/{i+1} correct)")

    return correct / len(test_cases) * 100, results


def evaluate_arc_easy(base_url, model, samples=None):
    """Evaluate ARC Easy - scientific reasoning."""
    test_cases = [
        {"q": "Which of the following is a property of water?", "options": ["A) It is a gas at room temperature", "B) It freezes at 0 degrees Celsius", "C) It is heavier than air", "D) It is transparent"], "a": "B"},
        {"q": "What causes day and night on Earth?", "options": ["A) The Moon orbiting Earth", "B) Earth rotating on its axis", "C) The Sun moving around Earth", "D) Clouds blocking sunlight"], "a": "B"},
        {"q": "Which planet is closest to the Sun?", "options": ["A) Venus", "B) Earth", "C) Mercury", "D) Mars"], "a": "C"},
        {"q": "What type of energy does a moving car have?", "options": ["A) Potential energy", "B) Kinetic energy", "C) Thermal energy", "D) Chemical energy"], "a": "B"},
        {"q": "Which organ pumps blood through the human body?", "options": ["A) Brain", "B) Lungs", "C) Heart", "D) Liver"], "a": "C"},
        {"q": "What is the process by which plants make food?", "options": ["A) Respiration", "B) Photosynthesis", "C) Digestion", "D) Fermentation"], "a": "B"},
        {"q": "Which state of matter has a definite shape and volume?", "options": ["A) Gas", "B) Liquid", "C) Solid", "D) Plasma"], "a": "C"},
        {"q": "What force keeps planets in orbit around the Sun?", "options": ["A) Magnetism", "B) Friction", "C) Gravity", "D) Inertia"], "a": "C"},
        {"q": "Which part of a plant absorbs water from soil?", "options": ["A) Leaves", "B) Stem", "C) Roots", "D) Flowers"], "a": "C"},
        {"q": "What is the smallest unit of an element?", "options": ["A) Molecule", "B) Atom", "C) Cell", "D) Electron"], "a": "B"},
        {"q": "Which layer of Earth do we live on?", "options": ["A) Core", "B) Mantle", "C) Crust", "D) Atmosphere"], "a": "C"},
        {"q": "What happens to water when it reaches 100 degrees Celsius?", "options": ["A) It freezes", "B) It evaporates", "C) It condenses", "D) It melts"], "a": "B"},
        {"q": "Which animal is a mammal?", "options": ["A) Snake", "B) Frog", "C) Dog", "D) Fish"], "a": "C"},
        {"q": "What is the main gas in Earth's atmosphere?", "options": ["A) Oxygen", "B) Carbon dioxide", "C) Nitrogen", "D) Hydrogen"], "a": "C"},
        {"q": "Which sense helps you detect light?", "options": ["A) Hearing", "B) Touch", "C) Sight", "D) Smell"], "a": "C"},
        {"q": "What type of rock is formed from cooled lava?", "options": ["A) Sedimentary", "B) Metamorphic", "C) Igneous", "D) Fossil"], "a": "C"},
        {"q": "Which planet is known as the Red Planet?", "options": ["A) Venus", "B) Mars", "C) Jupiter", "D) Saturn"], "a": "B"},
        {"q": "What is the function of red blood cells?", "options": ["A) Fight infection", "B) Carry oxygen", "C) Clot blood", "D) Digest food"], "a": "B"},
        {"q": "Which energy source is renewable?", "options": ["A) Coal", "B) Natural gas", "C) Solar power", "D) Oil"], "a": "C"},
        {"q": "What causes seasons on Earth?", "options": ["A) Distance from Sun", "B) Earth's tilted axis", "C) Moon's gravity", "D) Wind patterns"], "a": "B"},
        {"q": "Which material conducts electricity best?", "options": ["A) Rubber", "B) Plastic", "C) Copper", "D) Wood"], "a": "C"},
        {"q": "What is the boiling point of water in Fahrenheit?", "options": ["A) 100°F", "B) 180°F", "C) 212°F", "D) 32°F"], "a": "C"},
        {"q": "Which part of the cell contains DNA?", "options": ["A) Cytoplasm", "B) Nucleus", "C) Mitochondria", "D) Ribosome"], "a": "B"},
        {"q": "What type of animal eats only plants?", "options": ["A) Carnivore", "B) Omnivore", "C) Herbivore", "D) Scavenger"], "a": "C"},
        {"q": "Which force opposes motion between surfaces?", "options": ["A) Gravity", "B) Friction", "C) Magnetism", "D) Tension"], "a": "B"},
        {"q": "What is the largest organ in the human body?", "options": ["A) Heart", "B) Liver", "C) Skin", "D) Brain"], "a": "C"},
        {"q": "Which gas do plants absorb from the air?", "options": ["A) Oxygen", "B) Nitrogen", "C) Carbon dioxide", "D) Hydrogen"], "a": "C"},
        {"q": "What is the center of our solar system?", "options": ["A) Earth", "B) The Moon", "C) The Sun", "D) Jupiter"], "a": "C"},
        {"q": "Which type of wave can travel through a vacuum?", "options": ["A) Sound waves", "B) Water waves", "C) Light waves", "D) Seismic waves"], "a": "C"},
        {"q": "What is the pH of pure water?", "options": ["A) 0", "B) 7", "C) 14", "D) 1"], "a": "B"},
    ]

    if samples:
        test_cases = test_cases[:samples]

    correct = 0
    results = []

    for i, case in enumerate(test_cases):
        options_text = "\n".join(case["options"])
        messages = [
            {"role": "system", "content": "You are a helpful assistant that answers multiple-choice questions. Just give the letter of the correct answer."},
            {"role": "user", "content": f"Question: {case['q']}\n\nOptions:\n{options_text}\n\nAnswer with just the letter (A, B, C, or D):"},
        ]
        try:
            response = chat_completion(base_url, model, messages, max_tokens=2000)
            # Extract the letter
            answer = response.strip().upper()
            # Find first letter match
            for letter in ["A", "B", "C", "D"]:
                if letter in answer:
                    answer = letter
                    break
            is_correct = answer == case["a"]
            if is_correct:
                correct += 1
            results.append({"q": case["q"], "expected": case["a"], "got": answer, "correct": is_correct})
        except Exception as e:
            results.append({"q": case["q"], "expected": case["a"], "got": f"ERROR: {e}", "correct": False})

        if (i + 1) % 10 == 0:
            print(f"  ARC: {i+1}/{len(test_cases)} ({correct}/{i+1} correct)")

    return correct / len(test_cases) * 100, results


def evaluate_hellaswag(base_url, model, samples=None):
    """Evaluate HellaSwag - common sense completion."""
    test_cases = [
        {"context": "She put the milk in the", "completion": "refrigerator"},
        {"context": "The baby cried because it was", "completion": "hungry"},
        {"context": "He used a hammer to fix the", "completion": "nail"},
        {"context": "The sun rises in the", "completion": "east"},
        {"context": "She opened the door with her", "completion": "key"},
        {"context": "The chef cooked dinner in the", "completion": "kitchen"},
        {"context": "He drove the car to the", "completion": "store"},
        {"context": "The teacher wrote on the", "completion": "blackboard"},
        {"context": "She wore a coat because it was", "completion": "cold"},
        {"context": "The fish swam in the", "completion": "water"},
        {"context": "He read the book in the", "completion": "library"},
        {"context": "The bird flew across the", "completion": "sky"},
        {"context": "She baked a cake in the", "completion": "oven"},
        {"context": "The doctor examined the patient in the", "completion": "hospital"},
        {"context": "He planted flowers in the", "completion": "garden"},
        {"context": "The athlete ran on the", "completion": "track"},
        {"context": "She painted a picture with a", "completion": "brush"},
        {"context": "The computer crashed because of a", "completion": "virus"},
        {"context": "He cut the bread with a", "completion": "knife"},
        {"context": "The student studied for the", "completion": "exam"},
        {"context": "She washed her clothes in the", "completion": "washing machine"},
        {"context": "The pilot flew the plane to", "completion": "New York"},
        {"context": "He fixed the bicycle with a", "completion": "wrench"},
        {"context": "The singer performed on the", "completion": "stage"},
        {"context": "She wrote a letter with a", "completion": "pen"},
        {"context": "The farmer harvested crops from the", "completion": "field"},
        {"context": "He listened to music with", "completion": "headphones"},
        {"context": "The painter mixed colors on a", "completion": "palette"},
        {"context": "She ironed her shirt with an", "completion": "iron"},
        {"context": "The mechanic repaired the engine in the", "completion": "garage"},
    ]

    if samples:
        test_cases = test_cases[:samples]

    correct = 0
    results = []

    for i, case in enumerate(test_cases):
        messages = [
            {"role": "system", "content": "Complete the sentence naturally with a short phrase."},
            {"role": "user", "content": f"Complete: {case['context']}"},
        ]
        try:
            response = chat_completion(base_url, model, messages, max_tokens=2000)
            # Check if the expected completion is in the response (case-insensitive)
            is_correct = case["completion"].lower() in response.lower()
            if is_correct:
                correct += 1
            results.append({"context": case["context"], "expected": case["completion"], "got": response.strip(), "correct": is_correct})
        except Exception as e:
            results.append({"context": case["context"], "expected": case["completion"], "got": f"ERROR: {e}", "correct": False})

        if (i + 1) % 10 == 0:
            print(f"  HellaSwag: {i+1}/{len(test_cases)} ({correct}/{i+1} correct)")

    return correct / len(test_cases) * 100, results


def evaluate_piqa(base_url, model, samples=None):
    """Evaluate PIQA - physical reasoning."""
    test_cases = [
        {"goal": "How do you keep a cut apple from browning?", "sol1": "Put it in the freezer", "sol2": "Soak it in lemon juice", "correct": 2},
        {"goal": "How do you remove a splinter from your finger?", "sol1": "Push it deeper in", "sol2": "Use tweezers to pull it out", "correct": 2},
        {"goal": "How do you open a jar with a tight lid?", "sol1": "Run hot water over the lid", "sol2": "Hit it with a hammer", "correct": 1},
        {"goal": "How do you stop a running nose?", "sol1": "Blow it into a tissue", "sol2": "Hold your breath", "correct": 1},
        {"goal": "How do you clean a dirty window?", "sol1": "Wipe with glass cleaner and a cloth", "sol2": "Spray paint on it", "correct": 1},
        {"goal": "How do you cool down a hot cup of coffee?", "sol1": "Put it in the microwave", "sol2": "Add ice cubes", "correct": 2},
        {"goal": "How do you remove a stain from clothes?", "sol1": "Apply stain remover and wash", "sol2": "Iron directly on the stain", "correct": 1},
        {"goal": "How do you sharpen a pencil?", "sol1": "Use a sharpener", "sol2": "Bite the tip", "correct": 1},
        {"goal": "How do you measure the temperature of food?", "sol1": "Use a food thermometer", "sol2": "Touch it with your finger", "correct": 1},
        {"goal": "How do you prevent rust on metal tools?", "sol1": "Apply oil or paint", "sol2": "Leave them in water", "correct": 1},
        {"goal": "How do you unclog a drain?", "sol1": "Use a plunger or drain snake", "sol2": "Pour more water down it", "correct": 1},
        {"goal": "How do you keep bread fresh longer?", "sol1": "Store it in an airtight container", "sol2": "Leave it on the counter", "correct": 1},
        {"goal": "How do you remove a ring that's stuck on your finger?", "sol1": "Use soap and slide it off", "sol2": "Cut off your finger", "correct": 1},
        {"goal": "How do you make ice cream at home?", "sol1": "Use an ice cream maker or freeze mixture", "sol2": "Put milk in the sun", "correct": 1},
        {"goal": "How do you fix a wobbly chair?", "sol1": "Tighten the screws or add felt pads", "sol2": "Paint it a different color", "correct": 1},
        {"goal": "How do you remove gum from hair?", "sol1": "Apply oil and gently comb it out", "sol2": "Cut all your hair off", "correct": 1},
        {"goal": "How do you test if an egg is fresh?", "sol1": "Put it in water - fresh eggs sink", "sol2": "Smell it raw", "correct": 1},
        {"goal": "How do you prevent static electricity in clothes?", "sol1": "Use fabric softener", "sol2": "Wash with sand", "correct": 1},
        {"goal": "How do you remove a price tag sticker residue?", "sol1": "Use rubbing alcohol or peanut butter", "sol2": "Scrape with a knife", "correct": 1},
        {"goal": "How do you keep cut flowers fresh longer?", "sol1": "Change water and trim stems regularly", "sol2": "Put them in hot water", "correct": 1},
    ]

    if samples:
        test_cases = test_cases[:samples]

    correct = 0
    results = []

    for i, case in enumerate(test_cases):
        messages = [
            {"role": "system", "content": "You are given a goal and two possible solutions. Choose the more practical and effective solution. Answer with '1' or '2'."},
            {"role": "user", "content": f"Goal: {case['goal']}\n\nSolution 1: {case['sol1']}\nSolution 2: {case['sol2']}\n\nWhich solution is better? Answer 1 or 2:"},
        ]
        try:
            response = chat_completion(base_url, model, messages, max_tokens=2000)
            answer = response.strip()
            if "1" in answer and "2" not in answer:
                chosen = 1
            elif "2" in answer:
                chosen = 2
            else:
                chosen = -1
            is_correct = chosen == case["correct"]
            if is_correct:
                correct += 1
            results.append({"goal": case["goal"], "expected": case["correct"], "got": chosen, "correct": is_correct})
        except Exception as e:
            results.append({"goal": case["goal"], "expected": case["correct"], "got": f"ERROR: {e}", "correct": False})

        if (i + 1) % 10 == 0:
            print(f"  PIQA: {i+1}/{len(test_cases)} ({correct}/{i+1} correct)")

    return correct / len(test_cases) * 100, results


def evaluate_perplexity(base_url, model):
    """Evaluate perplexity using WikiText-2 test set via /v1/chat/completions with logprobs."""
    from datasets import load_dataset
    ds = load_dataset("wikitext", "wikitext-2-raw-v1", split="test")
    texts = [t.strip() for t in ds["text"] if t.strip()]
    corpus = "\n".join(texts)

    chunk_size = 4096
    chunks = []
    for i in range(0, len(corpus), chunk_size):
        chunk = corpus[i:i+chunk_size]
        if len(chunk) > 100:
            chunks.append(chunk)

    all_ppls = []
    total_tokens = 0

    for i, chunk in enumerate(chunks):
        url = f"{base_url}/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": chunk}],
            "max_tokens": 1,
            "temperature": 0,
            "logprobs": True,
        }
        try:
            resp = requests.post(url, json=payload, timeout=120)
            resp.raise_for_status()
            result = resp.json()
        except Exception as e:
            print(f"    Chunk {i+1}/{len(chunks)}: ERROR ({e})")
            continue

        choice = result.get("choices", [{}])[0]
        logprobs = choice.get("logprobs")
        if not logprobs:
            continue

        token_logprobs = []
        for lp in logprobs.get("content", []):
            if isinstance(lp, dict):
                token_logprobs.append(lp.get("logprob", 0))
            else:
                token_logprobs.append(lp)

        if not token_logprobs:
            continue

        mean_logprob = sum(token_logprobs) / len(token_logprobs)
        ppl = math.exp(-mean_logprob)
        all_ppls.append(ppl)
        total_tokens += len(token_logprobs)

        if (i + 1) % 50 == 0:
            print(f"    PPL: {i+1}/{len(chunks)} chunks ({total_tokens} tokens, avg PPL={sum(all_ppls)/len(all_ppls):.2f})")

    if not all_ppls:
        return None, None, 0

    log_ppls = [math.log(p) for p in all_ppls]
    geo_mean_ppl = math.exp(sum(log_ppls) / len(log_ppls))
    mean_ppl = sum(all_ppls) / len(all_ppls)

    return geo_mean_ppl, mean_ppl, total_tokens


def evaluate_humaneval(base_url, model, samples=None):
    """Evaluate HumanEval - code generation (pass@1)."""
    # Load dataset
    dataset_path = Path(__file__).parent.parent / "references" / "HumanEval.jsonl"
    if not dataset_path.exists():
        print(f"  ⚠️  HumanEval.jsonl not found at {dataset_path}. Skipping.")
        return 0, []

    with open(dataset_path) as f:
        test_cases = [json.loads(line) for line in f if line.strip()]

    if samples:
        test_cases = test_cases[:samples]

    correct = 0
    results = []

    for i, case in enumerate(test_cases):
        prompt = case["prompt"]
        test_code = case["test"]
        entry_point = case["entry_point"]
        task_id = case["task_id"]

        messages = [
            {"role": "system", "content": "You are an expert Python programmer. Complete the function. Return ONLY the code, no explanation."},
            {"role": "user", "content": prompt},
        ]
        try:
            response = chat_completion(base_url, model, messages, max_tokens=2000)

            # Extract code from response
            code = response.strip()

            # Strategy 1: Find ```python code blocks
            code_blocks = re.findall(r'```(?:python|py)?\s*\n(.*?)```', code, re.DOTALL)
            if code_blocks:
                code = code_blocks[0].strip()
            else:
                # Strategy 2: Find the function definition and extract from there
                # The prompt ends with "def entry_point(...):" so find it in the response
                func_pattern = rf'def\s+{re.escape(entry_point)}\s*\('
                match = re.search(func_pattern, code)
                if match:
                    code = code[match.start():]
                else:
                    # Strategy 3: Strip markdown wrappers
                    code = re.sub(r'^```(?:python|py)?\s*\n?', '', code, flags=re.IGNORECASE)
                    code = re.sub(r'\n?```\s*$', '', code)
                    code = code.strip()

            # Build the full test script
            full_code = f"""{prompt}{code}

{test_code}

# Run the tests
check({entry_point})
"""

            # Execute in isolated subprocess
            proc = subprocess.run(
                ["python3", "-c", full_code],
                capture_output=True,
                text=True,
                timeout=30,
            )

            is_correct = proc.returncode == 0
            if is_correct:
                correct += 1

            error_msg = proc.stderr.strip() if proc.returncode != 0 else ""
            results.append({
                "task_id": task_id,
                "entry_point": entry_point,
                "correct": is_correct,
                "error": error_msg[:200] if error_msg else "",
            })

        except subprocess.TimeoutExpired:
            results.append({"task_id": task_id, "entry_point": entry_point, "correct": False, "error": "TIMEOUT"})
        except Exception as e:
            results.append({"task_id": task_id, "entry_point": entry_point, "correct": False, "error": str(e)[:200]})

        if (i + 1) % 20 == 0:
            print(f"  HumanEval: {i+1}/{len(test_cases)} ({correct}/{i+1} pass@1)")

    return correct / len(test_cases) * 100, results


def main():
    parser = argparse.ArgumentParser(description="LLM Intelligence Benchmark")
    parser.add_argument("--host", default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    parser.add_argument("--model", default="qwen3.6-27b", help="Model name")
    parser.add_argument("--samples", type=int, default=None, help="Number of samples per task (default: all)")
    parser.add_argument("--output", default=None, help="Output JSON file path")
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"

    # Check server is alive
    try:
        resp = requests.get(f"{base_url}/v1/models", timeout=10)
        resp.raise_for_status()
        models = resp.json()["models"]
        print(f"✅ Server online. Available models: {[m['name'] for m in models]}")
    except Exception as e:
        print(f"❌ Server not reachable: {e}")
        sys.exit(1)

    print(f"\n🧠 Running intelligence benchmarks on {args.model}...")
    print("=" * 60)

    all_results = {}
    start_time = time.time()

    # Run benchmarks
    print("\n📐 GSM8K (Mathematical Reasoning)...")
    gsm8k_score, gsm8k_results = evaluate_gsm8k(base_url, args.model, args.samples)
    all_results["gsm8k"] = {"score": round(gsm8k_score, 1), "details": gsm8k_results}
    print(f"   ✅ GSM8K: {gsm8k_score:.1f}%")

    print("\n🔬 ARC Easy (Scientific Reasoning)...")
    arc_score, arc_results = evaluate_arc_easy(base_url, args.model, args.samples)
    all_results["arc_easy"] = {"score": round(arc_score, 1), "details": arc_results}
    print(f"   ✅ ARC Easy: {arc_score:.1f}%")

    print("\n🧩 HellaSwag (Common Sense)...")
    hellaswag_score, hellaswag_results = evaluate_hellaswag(base_url, args.model, args.samples)
    all_results["hellaswag"] = {"score": round(hellaswag_score, 1), "details": hellaswag_results}
    print(f"   ✅ HellaSwag: {hellaswag_score:.1f}%")

    print("\n🔧 PIQA (Physical Reasoning)...")
    piqa_score, piqa_results = evaluate_piqa(base_url, args.model, args.samples)
    all_results["piqa"] = {"score": round(piqa_score, 1), "details": piqa_results}
    print(f"   ✅ PIQA: {piqa_score:.1f}%")

    print("\n💻 HumanEval (Code Generation)...")
    humaneval_score, humaneval_results = evaluate_humaneval(base_url, args.model, args.samples)
    all_results["humaneval"] = {"score": round(humaneval_score, 1), "details": humaneval_results}
    print(f"   ✅ HumanEval: {humaneval_score:.1f}% pass@1")

    print("\n📉 Perplexity (WikiText-2) — baseline de calidad absoluta...")
    ppl_geo, ppl_mean, ppl_tokens = evaluate_perplexity(base_url, args.model)
    if ppl_geo is not None:
        all_results["perplexity"] = {
            "geometric_mean_ppl": round(ppl_geo, 4),
            "arithmetic_mean_ppl": round(ppl_mean, 4),
            "total_tokens": ppl_tokens,
        }
        print(f"   ✅ PPL (geometric mean): {ppl_geo:.4f}")
        print(f"   ✅ PPL (arithmetic mean): {ppl_mean:.4f}")
        print(f"   ✅ Tokens evaluados: {ppl_tokens}")
    else:
        all_results["perplexity"] = {"error": "No logprobs returned by server"}
        print(f"   ⚠️  PPL: servidor no devuelve logprobs")

    elapsed = time.time() - start_time

    # Summary
    print("\n" + "=" * 60)
    print("📊 RESULTS SUMMARY")
    print("=" * 60)
    print(f"{'Benchmark':<20} {'Score':>10} {'What it measures'}")
    print("-" * 60)
    print(f"{'GSM8K':<20} {gsm8k_score:>9.1f}% {'Mathematical reasoning'}")
    print(f"{'ARC Easy':<20} {arc_score:>9.1f}% {'Scientific reasoning'}")
    print(f"{'HellaSwag':<20} {hellaswag_score:>9.1f}% {'Common sense'}")
    print(f"{'PIQA':<20} {piqa_score:>9.1f}% {'Physical reasoning'}")
    print(f"{'HumanEval':<20} {humaneval_score:>9.1f}% {'Code generation (pass@1)'}")
    if ppl_geo is not None:
        print(f"{'PPL WikiText-2':<20} {ppl_geo:>9.4f} {'Absolute quality (lower=best)'}")
    avg = (gsm8k_score + arc_score + hellaswag_score + piqa_score) / 4
    print("-" * 60)
    print(f"{'AVERAGE':<20} {avg:>9.1f}%")
    print(f"{'HumanEval':<20} {humaneval_score:>9.1f}%")
    if ppl_geo is not None:
        print(f"{'PPL WikiText-2':<20} {ppl_geo:>9.4f}")
    print(f"\n⏱️  Time: {elapsed:.1f}s")

    # Save results
    output_path = args.output or f"/root/workspace/llm-eval-{args.model}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    output_data = {
        "model": args.model,
        "server": base_url,
        "timestamp": datetime.now().isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "scores": {
            "gsm8k": round(gsm8k_score, 1),
            "arc_easy": round(arc_score, 1),
            "hellaswag": round(hellaswag_score, 1),
            "piqa": round(piqa_score, 1),
            "humaneval": round(humaneval_score, 1),
            "average": round(avg, 1),
        },
        "perplexity": all_results.get("perplexity", {}),
        "details": all_results,
    }

    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)
    print(f"\n💾 Results saved to: {output_path}")


if __name__ == "__main__":
    main()
