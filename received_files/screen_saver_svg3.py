import pygame
import random
import svgpathtools
import numpy as np

# Initialize Pygame
pygame.init()

# Get the display's screen dimensions
screen_info = pygame.display.Info()
screen_width, screen_height = screen_info.current_w, screen_info.current_h

# Create the screen with the same dimensions
screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN)

# Set the title of the window
pygame.display.set_caption("SVG Tracing")

def parse_svg(svg_file):
    paths, _ = svgpathtools.svg2paths(svg_file)
    coordinates = []
    for path in paths:
        for segment in path:
            if hasattr(segment, 'point'):
                for t in np.linspace(0, 1, num=100):
                    point = segment.point(t)
                    coordinates.append((point.real, point.imag))
    return coordinates

def scale_coordinates(coordinates, max_width, max_height):
    min_x = min(coord[0] for coord in coordinates)
    max_x = max(coord[0] for coord in coordinates)
    min_y = min(coord[1] for coord in coordinates)
    max_y = max(coord[1] for coord in coordinates)

    x_scale = max_width / (max_x - min_x)
    y_scale = max_height / (max_y - min_y)
    scale = min(x_scale, y_scale) * 0.8  # Scale down a bit to fit within the screen with margin

    scaled_coords = []
    for x, y in coordinates:
        scaled_x = (x - min_x) * scale + (max_width - (max_x - min_x) * scale) / 2
        scaled_y = (y - min_y) * scale + (max_height - (max_y - min_y) * scale) / 2
        scaled_coords.append((scaled_x, scaled_y))
    return scaled_coords

# Define colors
black = (0, 0, 0)
green = (0, 255, 0)

# Load a font
font_size = 20
font = pygame.font.SysFont('courier', font_size, bold=True)

# Parse and scale SVG File for Coordinates
svg_file = 'forest.svg'
original_coordinates = parse_svg(svg_file)
scaled_coordinates = scale_coordinates(original_coordinates, screen_width, screen_height)

# Determine dynamic character count based on number of points
base_character_count = 20
character_count = base_character_count + len(scaled_coordinates) // 100

# Print out original and scaled coordinates for verification
print("Original Coordinates:")
for coord in original_coordinates:
    print(coord)

print("\nScaled Coordinates:")
for coord in scaled_coordinates:
    print(coord)

print(f"\nCharacter Count: {character_count}")

# Trailing effect surface
trail_surface = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)

# Initial speed modifier
speed_modifier = 0.5
character_spacing = 10  # Spacing between characters
positions = [random.randint(0, len(scaled_coordinates)-1) for _ in range(character_count)]  # Randomize initial positions

# Background effect variables
background_directions = ['vertical', 'horizontal', 'diagonal']
background_chars = [random.choice(background_directions) for _ in range(100)]

def draw_svg_trace():
    global positions

    for i in range(character_count):
        pos_index = int(positions[i]) % len(scaled_coordinates)
        x, y = scaled_coordinates[pos_index]

        char = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()_+-=[]{}|;':,.<>?/")
        char_surface = font.render(char, True, green)
        trail_surface.blit(char_surface, (x, y))

        # Move each character to the next point along the path
        positions[i] += speed_modifier

    # Ensure positions are wrapped around the path length
    positions = [pos % len(scaled_coordinates) for pos in positions]

def draw_background_effect():
    for i, direction in enumerate(background_chars):
        char = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()_+-=[]{}|;':,.<>?/")
        char_surface = font.render(char, True, green)

        if direction == 'vertical':
            x = i * (screen_width // len(background_chars))
            y = (pygame.time.get_ticks() * 0.05 + i * 20) % screen_height
        elif direction == 'horizontal':
            x = (pygame.time.get_ticks() * 0.05 + i * 20) % screen_width
            y = i * (screen_height // len(background_chars))
        elif direction == 'diagonal':
            x = (pygame.time.get_ticks() * 0.05 + i * 20) % screen_width
            y = (pygame.time.get_ticks() * 0.05 + i * 20) % screen_height

        trail_surface.blit(char_surface, (x, y))

def main():
    global speed_modifier, character_count

    running = True
    clock = pygame.time.Clock()

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    speed_modifier += 0.1
                elif event.key == pygame.K_DOWN:
                    speed_modifier = max(0.1, speed_modifier - 0.1)  # Allow speed to go below 1
                elif event.key == pygame.K_RIGHT:
                    character_count += 1
                    positions.append(random.randint(0, len(scaled_coordinates)-1))
                elif event.key == pygame.K_LEFT:
                    if character_count > 1:
                        character_count -= 1
                        positions.pop()

        # Draw the background effect
        trail_surface.fill((0, 0, 0, 50))  # Increased blur effect
        draw_background_effect()
        
        # Draw the SVG trace
        draw_svg_trace()

        # Update the display
        screen.blit(trail_surface, (0, 0))
        pygame.display.flip()
        clock.tick(60)  # Adjust tick rate as needed

    pygame.quit()

if __name__ == "__main__":
    main()
