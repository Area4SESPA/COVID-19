import math
from opentrons.types import Point
from opentrons import protocol_api
import time
import numpy as np
from timeit import default_timer as timer
import json
from datetime import datetime
import csv


# metadata
metadata = {
    'protocolName': 'Station B - RNA extraction - Generic',
    'author': 'Aitor Gastaminza & José Luis Villanueva & Alex Gasulla & Manuel Alba & Daniel Peñil & David Martínez',
    'source': 'HU Central de Asturias',
    'apiLevel': '2.5',
    'description': 'Protocol for RNA extraction'
}

################################################
# CHANGE THESE VARIABLES ONLY
################################################
NUM_SAMPLES                         = 96    # Must be multiple of 8
NUM_WASHES                          = 3     # Number of washes to do. Value between 0 - 3.
VOLUME_SAMPLE                       = 410   # Volume received from station A
BEADS_VOLUME_PER_SAMPLE             = 200
WASH_1_VOLUME_PER_SAMPLE            = 200
WASH_2_VOLUME_PER_SAMPLE            = 200
WASH_3_VOLUME_PER_SAMPLE            = 200
ELUTION_VOLUME_PER_SAMPLE           = 100
ELUTION_FINAL_VOLUME_PER_SAMPLE     = 100    # Volume transfered to final plates
BEADS_WELL_FIRST_TIME_NUM_MIXES     = 5
BEADS_WELL_NUM_MIXES                = 1
BEADS_NUM_MIXES                     = 10
WASH_1_NUM_MIXES                    = 10
WASH_2_NUM_MIXES                    = 10
WASH_3_NUM_MIXES                    = 10
ELUTION_NUM_MIXES                   = 10
TIP_RECYCLING_IN_WASH               = True
TIP_RECYCLING_IN_ELUTION            = True
PHOTOSENSITIVE                      = False # True if it has photosensitive reagents
################################################

run_id                      = 'B_Extraccion_total_Generico'

recycle_tip                 = False     # Do you want to recycle tips? It shoud only be set True for testing
mag_height                  = 7         # Height needed for NEST deepwell in magnetic deck
waste_drop_height           = 15
multi_well_rack_area        = 8 * 71    #Cross section of the 12 well reservoir
well_count                  = 0         # First reservoir well to use

num_cols = math.ceil(NUM_SAMPLES / 8) # Columns we are working on

def run(ctx: protocol_api.ProtocolContext):
    w1_tip_pos_list             = []
    w2_tip_pos_list             = []
    w3_tip_pos_list             = []
    elution_tip_pos_list        = []

    ctx.comment('Columnas a utilizar: '+str(num_cols))

    STEP = 0
    STEPS = { #Dictionary with STEP activation, description, and times
            1:{'Execute': BEADS_VOLUME_PER_SAMPLE > 0, 'description': 'Transferir bolas magnéticas'},
            2:{'Execute': True, 'description': 'Incubación con el imán ON', 'wait_time': 600}, 
            3:{'Execute': True, 'description': 'Desechar sobrenadante'},
            4:{'Execute': NUM_WASHES > 0, 'description': 'Imán OFF'},
            5:{'Execute': NUM_WASHES > 0, 'description': 'Transferir primer lavado'},
            6:{'Execute': NUM_WASHES > 0, 'description': 'Incubación con el imán ON', 'wait_time': 300},
            7:{'Execute': NUM_WASHES > 0, 'description': 'Desechar sobrenadante'},
            8:{'Execute': NUM_WASHES > 1, 'description': 'Imán OFF'},
            9:{'Execute': NUM_WASHES > 1, 'description': 'Transferir segundo lavado'},
            10:{'Execute': NUM_WASHES > 1, 'description': 'Incubación con el imán ON', 'wait_time': 300},
            11:{'Execute': NUM_WASHES > 1, 'description': 'Desechar sobrenadante'},
            12:{'Execute': NUM_WASHES > 2, 'description': 'Imán OFF'},
            13:{'Execute': NUM_WASHES > 2, 'description': 'Transferir tercer lavado'},
            14:{'Execute': NUM_WASHES > 2, 'description': 'Incubación con el imán ON', 'wait_time': 300},
            15:{'Execute': NUM_WASHES > 2, 'description': 'Desechar sobrenadante'},
            16:{'Execute': True, 'description': 'Secado', 'wait_time': 180},
            17:{'Execute': True, 'description': 'Imán OFF'},
            18:{'Execute': True, 'description': 'Transferir elución'},
            19:{'Execute': True, 'description': 'Incubación con el imán ON', 'wait_time': 180},
            20:{'Execute': True, 'description': 'Transferir elución a los pitufos'},
            }

    #Folder and file_path for log time
    import os
    folder_path = '/var/lib/jupyter/notebooks' + run_id
    if not ctx.is_simulating():
        if not os.path.isdir(folder_path):
            os.mkdir(folder_path)
        file_path = folder_path + '/Station_B_Extraccion_total_time_log.txt'

    #Define Reagents as objects with their properties
    class Reagent:
        def calc_vol_well(self):
            if(self.name == 'Sample'):
                self.num_wells = num_cols
                return VOLUME_SAMPLE
            else:    
                trips = math.ceil(self.reagent_volume / self.max_volume_allowed)
                vol_trip = self.reagent_volume / trips * 8
                max_trips_well = math.floor(11000 / vol_trip)
                total_trips = num_cols * trips
                self.num_wells = math.ceil(total_trips / max_trips_well)
                return math.ceil(total_trips / self.num_wells) * vol_trip + self.dead_vol

        def __init__(self, name, flow_rate_aspirate, flow_rate_dispense, flow_rate_aspirate_mix, flow_rate_dispense_mix,
        air_gap_vol_bottom, air_gap_vol_top, disposal_volume, rinse, max_volume_allowed, reagent_volume, h_cono, v_fondo, tip_recycling = 'none', dead_vol = 700, first_well = None):
            self.name = name
            self.flow_rate_aspirate = flow_rate_aspirate
            self.flow_rate_dispense = flow_rate_dispense
            self.flow_rate_aspirate_mix = flow_rate_aspirate_mix
            self.flow_rate_dispense_mix = flow_rate_dispense_mix
            self.air_gap_vol_bottom = air_gap_vol_bottom
            self.air_gap_vol_top = air_gap_vol_top
            self.disposal_volume = disposal_volume
            self.rinse = bool(rinse)
            self.max_volume_allowed = max_volume_allowed
            self.reagent_volume = reagent_volume
            self.col = 0
            self.vol_well = 0
            self.h_cono = h_cono
            self.v_cono = v_fondo
            self.tip_recycling = tip_recycling
            self.dead_vol = dead_vol
            self.first_well = first_well
            self.vol_well_original = self.calc_vol_well() if reagent_volume * NUM_SAMPLES > 0 else 0

    #Reagents and their characteristics
    Beads = Reagent(name = 'Beads',
                    flow_rate_aspirate = 25, #
                    flow_rate_dispense = 100, #
                    flow_rate_aspirate_mix = 25, #
                    flow_rate_dispense_mix = 100, #
                    air_gap_vol_bottom = 5,
                    air_gap_vol_top = 0,
                    disposal_volume = 1,
                    rinse = True,
                    max_volume_allowed = 180,
                    reagent_volume = BEADS_VOLUME_PER_SAMPLE, # reagent volume needed per sample
                    h_cono = 1.95,
                    v_fondo = 695, #1.95 * multi_well_rack_area / 2, #Prismatic
                    tip_recycling = 'A1')

    Wash_1 = Reagent(name = 'Wash 1',
                    flow_rate_aspirate = 25,
                    flow_rate_dispense = 100,
                    flow_rate_aspirate_mix = 25,
                    flow_rate_dispense_mix = 100,
                    air_gap_vol_bottom = 5,
                    air_gap_vol_top = 0,
                    disposal_volume = 1,
                    rinse = True,
                    max_volume_allowed = 180,
                    reagent_volume = WASH_1_VOLUME_PER_SAMPLE, 
                    h_cono = 1.95,
                    v_fondo = 695, #1.95 * multi_well_rack_area / 2, #Prismatic
                    tip_recycling = 'A1')

    Wash_2 = Reagent(name = 'Wash 2',
                    flow_rate_aspirate = 25,
                    flow_rate_dispense = 100,
                    flow_rate_aspirate_mix = 25,
                    flow_rate_dispense_mix = 100,
                    air_gap_vol_bottom = 5,
                    air_gap_vol_top = 0,
                    disposal_volume = 1,
                    rinse = True,
                    max_volume_allowed = 180,
                    reagent_volume = WASH_2_VOLUME_PER_SAMPLE, 
                    h_cono = 1.95,
                    v_fondo = 695, #1.95 * multi_well_rack_area / 2, #Prismatic
                    tip_recycling = 'A1')

    Wash_3 = Reagent(name = 'Wash 3',
                    flow_rate_aspirate = 25,
                    flow_rate_dispense = 100,
                    flow_rate_aspirate_mix = 25,
                    flow_rate_dispense_mix = 100,
                    air_gap_vol_bottom = 5,
                    air_gap_vol_top = 0,
                    disposal_volume = 1,
                    rinse = True,
                    max_volume_allowed = 180,
                    reagent_volume = WASH_3_VOLUME_PER_SAMPLE, 
                    h_cono = 1.95,
                    v_fondo = 695, #1.95 * multi_well_rack_area / 2, #Prismatic
                    tip_recycling = 'A1')

    Elution = Reagent(name = 'Elution',
                    flow_rate_aspirate = 25,
                    flow_rate_dispense = 100,
                    flow_rate_aspirate_mix = 25,
                    flow_rate_dispense_mix = 100,
                    air_gap_vol_bottom = 5,
                    air_gap_vol_top = 0,
                    disposal_volume = 1,
                    rinse = False,
                    max_volume_allowed = 180,
                    reagent_volume = ELUTION_VOLUME_PER_SAMPLE,
                    h_cono = 1.95,
                    v_fondo = 695) #1.95*multi_well_rack_area/2) #Prismatic

    Sample = Reagent(name = 'Sample',
                    flow_rate_aspirate = 5, # Original 0.5
                    flow_rate_dispense = 100, # Original 1
                    flow_rate_aspirate_mix = 1,
                    flow_rate_dispense_mix = 1,
                    air_gap_vol_bottom = 5,
                    air_gap_vol_top = 0,
                    disposal_volume = 1,
                    rinse = False,
                    max_volume_allowed = 180,
                    reagent_volume = VOLUME_SAMPLE,
                    h_cono = 4,
                    v_fondo = 4 * math.pi * 4**3 / 3) #Sphere

    Beads.vol_well      = Beads.vol_well_original
    Wash_1.vol_well     = Wash_1.vol_well_original
    Wash_2.vol_well     = Wash_2.vol_well_original
    Wash_3.vol_well     = Wash_3.vol_well_original
    Elution.vol_well    = Elution.vol_well_original
    Sample.vol_well     = 350 # Arbitrary value

    ctx.comment(' ')
    ctx.comment('###############################################')
    ctx.comment('VALORES DE VARIABLES')
    ctx.comment(' ')
    ctx.comment('Número de muestras: ' + str(NUM_SAMPLES)) 
    ctx.comment('Número de ciclos de lavado: ' + str(NUM_WASHES)) 
    ctx.comment('Volumen de muestra en el deepwell: ' + str(VOLUME_SAMPLE) + ' ul') 
    ctx.comment('Volumen de solución con bolas magnéticas por muestra: ' + str(BEADS_VOLUME_PER_SAMPLE) + ' ul')
    ctx.comment('Volumen del primer lavado por muestra: ' + str(WASH_1_VOLUME_PER_SAMPLE) + ' ul') 
    ctx.comment('Volumen del segundo lavado por muestra: ' + str(WASH_2_VOLUME_PER_SAMPLE) + ' ul') 
    ctx.comment('Volumen del tercer lavado por muestra: ' + str(WASH_3_VOLUME_PER_SAMPLE) + ' ul')
    ctx.comment('Volumen de elución por muestra: ' + str(ELUTION_VOLUME_PER_SAMPLE) + ' ul') 	
    ctx.comment('Volumen de elución a retirar del deepwell: ' + str(ELUTION_FINAL_VOLUME_PER_SAMPLE) + ' ul') 	 	
    ctx.comment('Número de mezclas en la primera recogida de un canal con bolas magnéticas: ' + str(BEADS_WELL_FIRST_TIME_NUM_MIXES))
    ctx.comment('Número de mezclas en el resto de recogidas de un canal con bolas magnéticas: ' + str(BEADS_WELL_NUM_MIXES)) 	
    ctx.comment('Número de mezclas con la solución de bolas magnéticas: ' + str(BEADS_NUM_MIXES))
    ctx.comment('Número de mezclas con el primer lavado: ' + str(WASH_1_NUM_MIXES)) 
    ctx.comment('Número de mezclas con el segundo lavado: ' + str(WASH_2_NUM_MIXES)) 
    ctx.comment('Número de mezclas con el tercer lavado: ' + str(WASH_3_NUM_MIXES)) 
    ctx.comment('Número de mezclas con la elución: ' + str(ELUTION_NUM_MIXES)) 	
    ctx.comment('Reciclado de puntas en los lavados activado: ' + str(TIP_RECYCLING_IN_WASH)) 
    ctx.comment('Reciclado de puntas en la elución activado: ' + str(TIP_RECYCLING_IN_ELUTION))
    ctx.comment('Foto-sensible: ' + str(PHOTOSENSITIVE)) 	
    ctx.comment(' ')

    #########
    def str_rounded(num):
        return str(int(num + 0.5))

    ###################
    #Custom functions
    def custom_mix(pipet, reagent, location, vol, rounds, blow_out, mix_height, offset, wait_time = 0, drop_height = -1, two_thirds_mix_bottom = False):
        '''
        Function for mix in the same location a certain number of rounds. Blow out optional. Offset
        can set to 0 or a higher/lower value which indicates the lateral movement
        '''
        if mix_height <= 0:
            mix_height = 1
        pipet.aspirate(1, location = location.bottom(z = mix_height), rate = reagent.flow_rate_aspirate_mix)
        for i in range(rounds):
            pipet.aspirate(vol, location = location.bottom(z = mix_height), rate = reagent.flow_rate_aspirate_mix)
            if two_thirds_mix_bottom and i < ((rounds / 3) * 2):
                pipet.dispense(vol, location = location.bottom(z = 5).move(Point(x = offset)), rate = reagent.flow_rate_dispense_mix)
            else:
                pipet.dispense(vol, location = location.top(z = drop_height).move(Point(x = offset)), rate = reagent.flow_rate_dispense_mix)
        pipet.dispense(1, location = location.bottom(z = mix_height), rate = reagent.flow_rate_dispense_mix)
        if blow_out == True:
            pipet.blow_out(location.top(z = -2)) # Blow out
        if wait_time != 0:
            ctx.delay(seconds=wait_time, msg='Esperando durante ' + str(wait_time) + ' segundos.')

    def calc_height(reagent, cross_section_area, aspirate_volume, min_height = 0.4):
        nonlocal ctx
        ctx.comment('Volumen útil restante ' + str(reagent.vol_well - reagent.dead_vol) +
                    ' < volumen necesario ' + str(aspirate_volume - Sample.disposal_volume * 8) + '?')
        if (reagent.vol_well - reagent.dead_vol + 1) < (aspirate_volume - Sample.disposal_volume * 8):
            ctx.comment('Se debe utilizar el siguiente canal')
            ctx.comment('Canal anterior: ' + str(reagent.col))
            # column selector position; intialize to required number
            reagent.col = reagent.col + 1
            ctx.comment(str('Nuevo canal: ' + str(reagent.col)))
            reagent.vol_well = reagent.vol_well_original
            ctx.comment('Nuevo volumen:' + str(reagent.vol_well))
            height = (reagent.vol_well - aspirate_volume - reagent.v_cono) / cross_section_area
                    #- reagent.h_cono
            reagent.vol_well = reagent.vol_well - (aspirate_volume - Sample.disposal_volume * 8)
            ctx.comment('Volumen restante:' + str(reagent.vol_well))
            if height < min_height:
                height = min_height
            col_change = True
        else:
            height = (reagent.vol_well - aspirate_volume - reagent.v_cono) / cross_section_area
            reagent.vol_well = reagent.vol_well - (aspirate_volume - (Sample.disposal_volume * 8))
            ctx.comment('La altura calculada es ' + str(height))
            if height < min_height:
                height = min_height
            ctx.comment('La altura usada es ' + str(height))
            col_change = False
        return height, col_change

    def move_vol_multi(pipet, reagent, source, dest, vol, x_offset_source, x_offset_dest, pickup_height, rinse, 
        avoid_droplet, wait_time, blow_out, touch_tip = False, touch_tip_v_offset = 0, drop_height = -5, 
        aspirate_with_x_scroll = False, dispense_bottom_air_gap_before = False):
        # Rinse before aspirating
        if rinse == True:
            custom_mix(pipet, reagent, location = source, vol = vol, rounds = 20, blow_out = False, mix_height = 3, offset = 0)

        # SOURCE
        if dispense_bottom_air_gap_before and reagent.air_gap_vol_bottom:
            pipet.dispense(reagent.air_gap_vol_bottom, source.top(z = -2), rate = reagent.flow_rate_dispense)

        if reagent.air_gap_vol_top != 0: #If there is air_gap_vol, switch pipette to slow speed
            pipet.move_to(source.top(z = 0))
            pipet.air_gap(reagent.air_gap_vol_top) #air gap

        if aspirate_with_x_scroll:
            aspirate_with_x_scrolling(pip = pipet, volume = vol, src = source, pickup_height = pickup_height, rate = reagent.flow_rate_aspirate, start_x_offset_src = 0, stop_x_offset_src = x_offset_source)
        else:    
            s = source.bottom(pickup_height).move(Point(x = x_offset_source))
            pipet.aspirate(vol, s, rate = reagent.flow_rate_aspirate) # aspirate liquid

        if reagent.air_gap_vol_bottom != 0: #If there is air_gap_vol, switch pipette to slow speed
            pipet.move_to(source.top(z = 0))
            pipet.air_gap(reagent.air_gap_vol_bottom) #air gap

        # if wait_time != 0:
        #     ctx.delay(seconds=wait_time, msg='Esperando durante ' + str(wait_time) + ' segundos.')

        if avoid_droplet == True: # Touch the liquid surface to avoid droplets
            ctx.comment("Moviendo a: " + str(pickup_height))
            pipet.move_to(source.bottom(pickup_height))

        # GO TO DESTINATION
        d = dest.top(z = drop_height).move(Point(x = x_offset_dest))
        pipet.dispense(vol - reagent.disposal_volume + reagent.air_gap_vol_bottom, d, rate = reagent.flow_rate_dispense)

        if reagent.air_gap_vol_top != 0:
            pipet.dispense(reagent.air_gap_vol_top, dest.top(z = 0), rate = reagent.flow_rate_dispense)

        if blow_out == True:
            pipet.blow_out(dest.top(z = drop_height))

        if touch_tip == True:
            pipet.touch_tip(speed = 20, v_offset = touch_tip_v_offset, radius=0.7)
            
        if wait_time != 0:
            ctx.delay(seconds=wait_time, msg='Esperando durante ' + str(wait_time) + ' segundos.')

        #if reagent.air_gap_vol_bottom != 0:
            #pipet.move_to(dest.top(z = 0))
            #pipet.air_gap(reagent.air_gap_vol_bottom) #air gap
            #pipet.aspirate(air_gap_vol_bottom, dest.top(z = 0),rate = reagent.flow_rate_aspirate) #air gap

    def aspirate_with_x_scrolling(pip, volume, src, pickup_height = 0, rate = 1, start_x_offset_src = 0, stop_x_offset_src = 0):

        max_asp = volume/pip.min_volume
        inc_step = (start_x_offset_src - stop_x_offset_src) / max_asp

        for x in reversed(np.arange(stop_x_offset_src, start_x_offset_src, inc_step)):
            s = src.bottom(pickup_height).move(Point(x = x))
            pip.aspirate(volume = pip.min_volume, location = s, rate = rate)

    ##########
    # pick up tip and if there is none left, prompt user for a new rack
    def pick_up(pip, position = None):
        nonlocal tip_track
        #if not ctx.is_simulating():
        if recycle_tip:
            pip.pick_up_tip(tips300[0].wells()[0])
        else:
            if tip_track['counts'][pip] >= tip_track['maxes'][pip]:
                for i in range(3):
                    ctx._hw_manager.hardware.set_lights(rails=False)
                    ctx._hw_manager.hardware.set_lights(button=(1, 0 ,0))
                    time.sleep(0.3)
                    ctx._hw_manager.hardware.set_lights(rails=True)
                    ctx._hw_manager.hardware.set_lights(button=(0, 0 ,1))
                    time.sleep(0.3)
                ctx._hw_manager.hardware.set_lights(button=(0, 1 ,0))
                ctx.pause('Reemplaza las cajas de puntas de ' + str(pip.max_volume) + 'µl antes \
                de continuar.')
                pip.reset_tipracks()
                tip_track['counts'][pip] = 0
                tip_track['num_refills'][pip] += 1
            if position is None:
                pip.pick_up_tip()
            else:
                pip.pick_up_tip(position)

    def start_run():
        ctx.comment(' ')
        ctx.comment('###############################################')
        ctx.comment('Empezando protocolo')
        if PHOTOSENSITIVE == False:
            ctx._hw_manager.hardware.set_lights(button = True, rails =  True)
        else:
            ctx._hw_manager.hardware.set_lights(button = True, rails =  False)
        now = datetime.now()
        # dd/mm/YY H:M:S
        start_time = now.strftime("%Y/%m/%d %H:%M:%S")
        return start_time

    def finish_run():
        ctx.comment('###############################################')
        ctx.comment('Protocolo finalizado')
        ctx.comment(' ')
        #Set light color to blue
        ctx._hw_manager.hardware.set_lights(button = True, rails =  False)
        now = datetime.now()
        # dd/mm/YY H:M:S
        finish_time = now.strftime("%Y/%m/%d %H:%M:%S")
        if PHOTOSENSITIVE==False:
            for i in range(10):
                ctx._hw_manager.hardware.set_lights(button = False, rails =  False)
                time.sleep(0.3)
                ctx._hw_manager.hardware.set_lights(button = True, rails =  True)
                time.sleep(0.3)
        else:
            for i in range(10):
                ctx._hw_manager.hardware.set_lights(button = False, rails =  False)
                time.sleep(0.3)
                ctx._hw_manager.hardware.set_lights(button = True, rails =  False)
                time.sleep(0.3)
        ctx._hw_manager.hardware.set_lights(button = True, rails =  False)

        used_tips = tip_track['num_refills'][m300] * 96 * len(m300.tip_racks) + tip_track['counts'][m300]
        ctx.comment('Puntas de 200 ul utilizadas: ' + str(used_tips) + ' (' + str(round(used_tips / 96, 2)) + ' caja(s))')
        ctx.comment('###############################################')

        return finish_time

    def log_step_start():
        ctx.comment(' ')
        ctx.comment('###############################################')
        ctx.comment('PASO '+str(STEP)+': '+STEPS[STEP]['description'])
        ctx.comment('###############################################')
        ctx.comment(' ')
        return datetime.now()

    def log_step_end(start):
        end = datetime.now()
        time_taken = (end - start)
        STEPS[STEP]['Time:'] = str(time_taken)

        ctx.comment(' ')
        ctx.comment('Paso ' + str(STEP) + ': ' +STEPS[STEP]['description'] + ' hizo un tiempo de ' + str(time_taken))
        ctx.comment(' ')

    ##########
    def find_side(col):
        if col%2 == 0:
            side = -1 # left
        else:
            side = 1 # right
        return side

    def assign_wells(reagent):
        global well_count
        reagent.first_well = well_count + 1
        reagent.reagent_reservoir = reagent_res.rows()[0][well_count:well_count + reagent.num_wells]
        well_count += reagent.num_wells
        ctx.comment(reagent.name + ': ' + str(reagent.num_wells) + ' canales desde el canal '+ str(reagent.first_well) +' en el reservorio de 12 canales con un volumen de ' + str_rounded(reagent.vol_well_original) + ' uL cada uno')

####################################
    # load labware and modules
    ######## 12 well rack
    reagent_res = ctx.load_labware('nest_12_reservoir_15ml', '5','reagent deepwell plate')

##################################
    ####### Elution plate - final plate, goes to C
    elution_plate = ctx.load_labware('rochemagnapure_96_wellplate_400ul', '1','ROCHE MagnaPure 96 Well Plate 400 uL')

############################################
    ######## Deepwell - comes from A
    magdeck = ctx.load_module('Magnetic Module Gen2', '4')
    deepwell_plate = magdeck.load_labware('nest_96_wellplate_2ml_deep', 'NEST 96 Deepwell Plate 2mL') # Change to NEST deepwell plate.
    
####################################
    ######## Waste reservoir
    waste_reservoir = ctx.load_labware('nest_1_reservoir_195ml', '7', 'waste reservoir') # Change to our waste reservoir
    waste = waste_reservoir.wells()[0] # referenced as reservoir

####################################
    ######### Load tip_racks
    tips300 = [ctx.load_labware('opentrons_96_tiprack_300ul', slot, '200µl filter tiprack')
        for slot in ['3', '6', '8', '9', '10', '11']]

###############################################################################
    #Declare which reagents are in each reservoir as well as deepwell and elution plate
    ctx.comment(' ')
    ctx.comment('###############################################')
    ctx.comment('VOLÚMENES PARA ' + str(NUM_SAMPLES) + ' MUESTRAS')
    ctx.comment(' ')
    if BEADS_VOLUME_PER_SAMPLE > 0:
        assign_wells(Beads)
    
    if NUM_WASHES > 0:
        assign_wells(Wash_1)
        if NUM_WASHES > 1:
            assign_wells(Wash_2)
            if NUM_WASHES > 2:
                assign_wells(Wash_3)

    assign_wells(Elution)
    ctx.comment('###############################################')
    ctx.comment(' ')

    work_destinations           = deepwell_plate.rows()[0][:Sample.num_wells]
    final_destinations          = elution_plate.rows()[0][:Sample.num_wells]

    # pipettes.
    m300 = ctx.load_instrument('p300_multi_gen2', 'left', tip_racks = tips300) # Load multi pipette

    #### used tip counter and set maximum tips available
    tip_track = {
        'counts': {m300: 0},
        'maxes': {m300: 96 * len(m300.tip_racks)}, #96 tips per tiprack * number or tipracks in the layout
        'num_refills' : {m300 : 0},
        'tips': { m300: [tip for rack in tips300 for tip in rack.rows()[0]]}
        }

###############################################################################
    start_run()
    magdeck.disengage()

    ###############################################################################
    # STEP 1 Transferir bolas magnéticas
    ########
    STEP += 1
    if STEPS[STEP]['Execute']==True:
    #Transferir bolas magnéticas
        start = log_step_start()

        beads_trips = math.ceil(Beads.reagent_volume / Beads.max_volume_allowed)
        beads_volume = Beads.reagent_volume / beads_trips
        beads_transfer_vol = []
        for i in range(beads_trips):
            beads_transfer_vol.append(beads_volume + Beads.disposal_volume)
        x_offset_source = 0
        x_offset_dest   = 0
        rinse = False # Original: True 
        first_mix_done = False

        for i in range(num_cols):
            ctx.comment("Column: " + str(i))
            if not m300.hw_pipette['has_tip']:
                pick_up(m300)
            for j,transfer_vol in enumerate(beads_transfer_vol):
                #Calculate pickup_height based on remaining volume and shape of container
                # transfer_vol_extra = transfer_vol if j > 0 else transfer_vol + 100  # Extra 100 isopropanol for calcs
                # [pickup_height, change_col] = calc_height(Beads, multi_well_rack_area, transfer_vol_extra * 8)    
                [pickup_height, change_col] = calc_height(Beads, multi_well_rack_area, transfer_vol * 8)    
                if change_col == True or not first_mix_done: #If we switch column because there is not enough volume left in current reservoir column we mix new column
                    ctx.comment('Mezclando nuevo canal del reservorio: ' + str(Beads.col + 1))
                    custom_mix(m300, Beads, Beads.reagent_reservoir[Beads.col],
                        vol = Beads.max_volume_allowed, rounds = BEADS_WELL_FIRST_TIME_NUM_MIXES, 
                        blow_out = False, mix_height = 1.5, offset = 0)
                    first_mix_done = True
                else:
                    ctx.comment('Mezclando canal del reservorio: ' + str(Beads.col + 1))
                    mix_height = 1.5 if pickup_height > 1.5 else pickup_height
                    custom_mix(m300, Beads, Beads.reagent_reservoir[Beads.col],
                        vol = Beads.max_volume_allowed, rounds = BEADS_WELL_NUM_MIXES, 
                        blow_out = False, mix_height = mix_height, offset = 0)

                ctx.comment('Aspirando desde la columna del reservorio: ' + str(Beads.col + 1))
                ctx.comment('La altura de recogida es ' + str(pickup_height))
                move_vol_multi(m300, reagent = Beads, source = Beads.reagent_reservoir[Beads.col],
                        dest = work_destinations[i], vol = transfer_vol, x_offset_source = x_offset_source, x_offset_dest = x_offset_dest,
                        pickup_height = pickup_height, rinse = rinse, avoid_droplet = False, wait_time = 0, blow_out = True, touch_tip = False, drop_height = 1)
            
            if BEADS_NUM_MIXES > 0:
                ctx.comment(' ')
                ctx.comment('Mezclando muestra ')
                custom_mix(m300, Beads, location = work_destinations[i], vol =  Beads.max_volume_allowed,
                        rounds = BEADS_NUM_MIXES, blow_out = False, mix_height = 1, offset = 0, wait_time = 2)
            
            m300.move_to(work_destinations[i].top(0))
            m300.air_gap(Beads.air_gap_vol_bottom) #air gap

            if recycle_tip == True:
                m300.return_tip()
            else:
                m300.drop_tip(home_after = False)
            tip_track['counts'][m300] += 8        
            
        log_step_end(start)
        ###############################################################################
        # STEP 1 Transferir bolas magnéticas
        ########
    
    ###############################################################################
    # STEP 2 Incubación con el imán ON
    ########
    STEP += 1
    if STEPS[STEP]['Execute']==True:
        start = log_step_start()

        ctx.comment(' ')
        magdeck.engage(height = mag_height)
        ctx.delay(seconds = STEPS[STEP]['wait_time'], msg = 'Incubación con el imán ON durante ' + format(STEPS[STEP]['wait_time']) + ' segundos.')
        ctx.comment(' ')

        log_step_end(start)
        ###############################################################################
        # STEP 2 Incubación con el imán ON
        ########

    ###############################################################################
    # STEP 3 Desechar sobrenadante
    ########
    STEP += 1
    if STEPS[STEP]['Execute']==True:
        start = log_step_start()

        supernatant_trips = math.ceil((Sample.reagent_volume + Beads.reagent_volume) / Sample.max_volume_allowed)
        supernatant_volume = Sample.max_volume_allowed # We try to remove an exceeding amount of supernatant to make sure it is empty
        supernatant_transfer_vol = []
        for i in range(supernatant_trips):
            supernatant_transfer_vol.append(supernatant_volume + Sample.disposal_volume)
        
        x_offset_rs = 2
        pickup_height = 0.5 # Original 0.5

        for i in range(num_cols):
            x_offset_source = find_side(i) * x_offset_rs
            x_offset_dest   = 0
            not_first_transfer = False

            if not m300.hw_pipette['has_tip']:
                pick_up(m300)
            for transfer_vol in supernatant_transfer_vol:
                ctx.comment('Aspirando de la columna del deepwell: ' + str(i+1))
                ctx.comment('La altura de recogida es ' + str(pickup_height) )

                move_vol_multi(m300, reagent = Sample, source = work_destinations[i],
                        dest = waste, vol = transfer_vol, x_offset_source = x_offset_source, x_offset_dest = x_offset_dest,
                        pickup_height = pickup_height, rinse = False, avoid_droplet = False, wait_time = 2, blow_out = True,
                        dispense_bottom_air_gap_before = not_first_transfer, drop_height = waste_drop_height)
                m300.move_to(waste.top(z = waste_drop_height))
                m300.air_gap(Sample.air_gap_vol_bottom)
                not_first_transfer = True

            if recycle_tip == True:
                m300.return_tip()
            else:
                m300.drop_tip(home_after = False)
            tip_track['counts'][m300] += 8

        log_step_end(start)
        ###############################################################################
        # STEP 3 Desechar sobrenadante
        ########

    ###############################################################################
    # STEP 4 MAGNET OFF
    ########
    STEP += 1
    if STEPS[STEP]['Execute']==True:
        start = log_step_start()

        # Imán OFF
        magdeck.disengage()

        log_step_end(start)
        ###############################################################################
        # STEP 4 MAGNET OFF
        ########

    ###############################################################################
    # STEP 5 Transferir primer lavado
    ########
    STEP += 1
    if STEPS[STEP]['Execute']==True:
        start = log_step_start()

        wash_trips = math.ceil(Wash_1.reagent_volume / Wash_1.max_volume_allowed)
        wash_volume = Wash_1.reagent_volume / wash_trips #136.66
        wash_transfer_vol = []
        for i in range(wash_trips):
            wash_transfer_vol.append(wash_volume + Wash_1.disposal_volume)
        x_offset_rs = 2.5
        rinse = False # Not needed

        for i in range(num_cols):
            x_offset_source = 0
            x_offset_dest   = -1 * find_side(i) * x_offset_rs
            if not m300.hw_pipette['has_tip']:
                pick_up(m300)
                if TIP_RECYCLING_IN_WASH:
                    w1_tip_pos_list += [tip_track['tips'][m300][int(tip_track['counts'][m300] / 8)]]
            for transfer_vol in wash_transfer_vol:
                #Calculate pickup_height based on remaining volume and shape of container
                [pickup_height, change_col] = calc_height(Wash_1, multi_well_rack_area, transfer_vol*8)
                ctx.comment('Aspirando desde la columna del reservorio: ' + str(Wash_1.col))
                ctx.comment('La altura de recogida es ' + str(pickup_height))

                move_vol_multi(m300, reagent = Wash_1, source = Wash_1.reagent_reservoir[Wash_1.col],
                        dest = work_destinations[i], vol = transfer_vol, x_offset_source = x_offset_source, x_offset_dest = x_offset_dest,
                        pickup_height = pickup_height, rinse = rinse, avoid_droplet = False, wait_time = 0, blow_out = False)
            
            if WASH_1_NUM_MIXES > 0:
                custom_mix(m300, Wash_1, location = work_destinations[i], vol = 180, two_thirds_mix_bottom = True,
                        rounds = WASH_1_NUM_MIXES, blow_out = False, mix_height = 1.5, offset = x_offset_dest)
            
            m300.move_to(work_destinations[i].top(0))
            m300.air_gap(Wash_1.air_gap_vol_bottom) #air gap

            if recycle_tip == True or TIP_RECYCLING_IN_WASH == True:
                m300.return_tip()
            else:
                m300.drop_tip(home_after = False)
            tip_track['counts'][m300] += 8

        log_step_end(start)
        ###############################################################################
        # STEP 5 ADD WASH
        ########

    ###############################################################################
    # STEP 6 Incubación con el imán ON
    ########
    STEP += 1
    if STEPS[STEP]['Execute']==True:
        start = log_step_start()

        # switch on magnet
        magdeck.engage(mag_height)
        ctx.delay(seconds=STEPS[STEP]['wait_time'], msg='Incubación con el imán ON durante ' + format(STEPS[STEP]['wait_time']) + ' segundos.')

        log_step_end(start)
        ####################################################################
        # STEP 6 Incubación con el imán ON
        ########

    ###############################################################################
    # STEP 7 Desechar sobrenadante
    ########
    STEP += 1
    if STEPS[STEP]['Execute']==True:
        start = log_step_start()

        supernatant_trips = math.ceil(Wash_1.reagent_volume / Wash_1.max_volume_allowed)
        supernatant_volume = Wash_1.max_volume_allowed # We try to remove an exceeding amount of supernatant to make sure it is empty
        supernatant_transfer_vol = []
        for i in range(supernatant_trips):
            supernatant_transfer_vol.append(supernatant_volume + Sample.disposal_volume)
        
        x_offset_rs = 2
        pickup_height = 0.5 # Original 0.5

        for i in range(num_cols):
            x_offset_source = find_side(i) * x_offset_rs
            x_offset_dest   = 0
            not_first_transfer = False

            if not m300.hw_pipette['has_tip']:
                if TIP_RECYCLING_IN_WASH:
                    pick_up(m300, w1_tip_pos_list[i])
                    m300.dispense(Wash_1.air_gap_vol_top, work_destinations[i].top(z = 0), rate = Wash_1.flow_rate_dispense)
                else:
                    pick_up(m300)
            for transfer_vol in supernatant_transfer_vol:
                #Pickup_height is fixed here
                ctx.comment('Aspirando de la columna del deepwell: ' + str(i+1))
                ctx.comment('La altura de recogida es ' + str(pickup_height) )
                move_vol_multi(m300, reagent = Sample, source = work_destinations[i],
                    dest = waste, vol = transfer_vol, x_offset_source = x_offset_source, x_offset_dest = x_offset_dest,
                    pickup_height = pickup_height, rinse = False, avoid_droplet = False, wait_time = 2, blow_out = False,
                    dispense_bottom_air_gap_before = not_first_transfer, drop_height = waste_drop_height)
                m300.move_to(waste.top(z = waste_drop_height))
                m300.air_gap(Sample.air_gap_vol_bottom)
                not_first_transfer = True

            if recycle_tip == True:
                m300.return_tip()
            else:
                m300.drop_tip(home_after = False)
            if not TIP_RECYCLING_IN_WASH:
                tip_track['counts'][m300] += 8

        log_step_end(start)
        ###############################################################################
        # STEP 7 Desechar sobrenadante
        ########

    ###############################################################################
    # STEP 8 MAGNET OFF
    ########
    STEP += 1
    if STEPS[STEP]['Execute']==True:
        start = log_step_start()

        # Imán OFF
        magdeck.disengage()

        log_step_end(start)
        ###############################################################################
        # STEP 8 MAGNET OFF
        ########

    ###############################################################################
    # STEP 9 Transferir segundo lavado
    ########
    STEP += 1
    if STEPS[STEP]['Execute']==True:
        start = log_step_start()

        wash_trips = math.ceil(Wash_2.reagent_volume / Wash_2.max_volume_allowed)
        wash_volume = Wash_2.reagent_volume / wash_trips #136.66
        wash_transfer_vol = []
        for i in range(wash_trips):
            wash_transfer_vol.append(wash_volume + Wash_2.disposal_volume)
        x_offset_rs = 2.5
        rinse = False # Not needed

        for i in range(num_cols):
            x_offset_source = 0
            x_offset_dest   = -1 * find_side(i) * x_offset_rs
            if not m300.hw_pipette['has_tip']:
                pick_up(m300)
                if TIP_RECYCLING_IN_WASH:
                    w2_tip_pos_list += [tip_track['tips'][m300][int(tip_track['counts'][m300] / 8)]]
            for transfer_vol in wash_transfer_vol:
                #Calculate pickup_height based on remaining volume and shape of container
                [pickup_height, change_col] = calc_height(Wash_2, multi_well_rack_area, transfer_vol*8)
                ctx.comment('Aspirando desde la columna del reservorio: ' + str(Wash_2.col))
                ctx.comment('La altura de recogida es ' + str(pickup_height))

                move_vol_multi(m300, reagent = Wash_2, source = Wash_2.reagent_reservoir[Wash_2.col],
                        dest = work_destinations[i], vol = transfer_vol, x_offset_source = x_offset_source, x_offset_dest = x_offset_dest,
                        pickup_height = pickup_height, rinse = rinse, avoid_droplet = False, wait_time = 0, blow_out = False)
            
            if WASH_2_NUM_MIXES > 0:
                custom_mix(m300, Wash_2, location = work_destinations[i], vol = 180, two_thirds_mix_bottom = True,
                        rounds = WASH_2_NUM_MIXES, blow_out = False, mix_height = 1.5, offset = x_offset_dest)
            
            m300.move_to(work_destinations[i].top(0))
            m300.air_gap(Wash_2.air_gap_vol_bottom) #air gap

            if recycle_tip == True or TIP_RECYCLING_IN_WASH == True:
                m300.return_tip()
            else:
                m300.drop_tip(home_after = False)
            tip_track['counts'][m300] += 8

        log_step_end(start)
        ###############################################################################
        # STEP 9 ADD WASH
        ########

    ###############################################################################
    # STEP 10 Incubación con el imán ON
    ########
    STEP += 1
    if STEPS[STEP]['Execute']==True:
        start = log_step_start()

        # switch on magnet
        magdeck.engage(mag_height)
        ctx.delay(seconds=STEPS[STEP]['wait_time'], msg='Incubación con el imán ON durante ' + format(STEPS[STEP]['wait_time']) + ' segundos.')

        log_step_end(start)
        ####################################################################
        # STEP 10 Incubación con el imán ON
        ########

    ###############################################################################
    # STEP 11 Desechar sobrenadante
    ########
    STEP += 1
    if STEPS[STEP]['Execute']==True:
        start = log_step_start()

        supernatant_trips = math.ceil(Wash_2.reagent_volume / Wash_2.max_volume_allowed)
        supernatant_volume = Wash_2.max_volume_allowed # We try to remove an exceeding amount of supernatant to make sure it is empty
        supernatant_transfer_vol = []
        for i in range(supernatant_trips):
            supernatant_transfer_vol.append(supernatant_volume + Sample.disposal_volume)
        
        x_offset_rs = 2
        pickup_height = 0.5 # Original 0.5

        for i in range(num_cols):
            x_offset_source = find_side(i) * x_offset_rs
            x_offset_dest   = 0
            not_first_transfer = False

            if not m300.hw_pipette['has_tip']:
                if TIP_RECYCLING_IN_WASH:
                    pick_up(m300, w2_tip_pos_list[i])
                    m300.dispense(Wash_2.air_gap_vol_top, work_destinations[i].top(z = 0), rate = Wash_2.flow_rate_dispense)
                else:
                    pick_up(m300)
            for transfer_vol in supernatant_transfer_vol:
                #Pickup_height is fixed here
                ctx.comment('Aspirando de la columna del deepwell: ' + str(i+1))
                ctx.comment('La altura de recogida es ' + str(pickup_height) )
                move_vol_multi(m300, reagent = Sample, source = work_destinations[i],
                    dest = waste, vol = transfer_vol, x_offset_source = x_offset_source, x_offset_dest = x_offset_dest,
                    pickup_height = pickup_height, rinse = False, avoid_droplet = False, wait_time = 2, blow_out = False,
                    dispense_bottom_air_gap_before = not_first_transfer, drop_height = waste_drop_height)
                m300.move_to(waste.top(z = waste_drop_height))
                m300.air_gap(Sample.air_gap_vol_bottom)
                not_first_transfer = True

            if recycle_tip == True:
                m300.return_tip()
            else:
                m300.drop_tip(home_after = False)
            if not TIP_RECYCLING_IN_WASH:
                tip_track['counts'][m300] += 8

        log_step_end(start)
        ###############################################################################
        # STEP 11 Desechar sobrenadante
        ########

    ###############################################################################
    # STEP 12 MAGNET OFF
    ########
    STEP += 1
    if STEPS[STEP]['Execute']==True:
        start = log_step_start()

        # Imán OFF
        magdeck.disengage()

        log_step_end(start)
        ###############################################################################
        # STEP 12 MAGNET OFF
        ########

    ###############################################################################
    # STEP 13 Transferir tercer lavado
    ########
    STEP += 1
    if STEPS[STEP]['Execute']==True:
        start = log_step_start()

        wash_trips = math.ceil(Wash_3.reagent_volume / Wash_3.max_volume_allowed)
        wash_volume = Wash_3.reagent_volume / wash_trips #136.66
        wash_transfer_vol = []
        for i in range(wash_trips):
            wash_transfer_vol.append(wash_volume + Wash_3.disposal_volume)
        x_offset_rs = 2.5
        rinse = False # Not needed

        for i in range(num_cols):
            x_offset_source = 0
            x_offset_dest   = -1 * find_side(i) * x_offset_rs
            if not m300.hw_pipette['has_tip']:
                pick_up(m300)
                if TIP_RECYCLING_IN_WASH:
                    w3_tip_pos_list += [tip_track['tips'][m300][int(tip_track['counts'][m300] / 8)]]
            for transfer_vol in wash_transfer_vol:
                #Calculate pickup_height based on remaining volume and shape of container
                [pickup_height, change_col] = calc_height(Wash_3, multi_well_rack_area, transfer_vol*8)
                ctx.comment('Aspirando desde la columna del reservorio: ' + str(Wash_3.col))
                ctx.comment('La altura de recogida es ' + str(pickup_height))

                move_vol_multi(m300, reagent = Wash_3, source = Wash_3.reagent_reservoir[Wash_3.col],
                        dest = work_destinations[i], vol = transfer_vol, x_offset_source = x_offset_source, x_offset_dest = x_offset_dest,
                        pickup_height = pickup_height, rinse = rinse, avoid_droplet = False, wait_time = 0, blow_out = False)
            
            if WASH_3_NUM_MIXES > 0:
                custom_mix(m300, Wash_3, location = work_destinations[i], vol = 180, two_thirds_mix_bottom = True,
                        rounds = WASH_3_NUM_MIXES, blow_out = False, mix_height = 1.5, offset = x_offset_dest)
            
            m300.move_to(work_destinations[i].top(0))
            m300.air_gap(Wash_3.air_gap_vol_bottom) #air gap

            if recycle_tip == True or TIP_RECYCLING_IN_WASH == True:
                m300.return_tip()
            else:
                m300.drop_tip(home_after = False)
            tip_track['counts'][m300] += 8

        log_step_end(start)
        ###############################################################################
        # STEP 13 Transferir tercer lavado
        ########

    ###############################################################################
    # STEP 14 Incubación con el imán ON
    ########
    STEP += 1
    if STEPS[STEP]['Execute']==True:
        start = log_step_start()

        # switch on magnet
        magdeck.engage(mag_height)
        ctx.delay(seconds=STEPS[STEP]['wait_time'], msg='Incubación con el imán ON durante ' + format(STEPS[STEP]['wait_time']) + ' segundos.')

        log_step_end(start)
        ####################################################################
        # STEP 14 Incubación con el imán ON
        ########

    ###############################################################################
    # STEP 15 Desechar sobrenadante
    ########
    STEP += 1
    if STEPS[STEP]['Execute']==True:
        start = log_step_start()

        supernatant_trips = math.ceil(Wash_3.reagent_volume / Wash_3.max_volume_allowed)
        supernatant_volume = Wash_3.max_volume_allowed # We try to remove an exceeding amount of supernatant to make sure it is empty
        supernatant_transfer_vol = []
        for i in range(supernatant_trips):
            supernatant_transfer_vol.append(supernatant_volume + Sample.disposal_volume)
        
        x_offset_rs = 2
        pickup_height = 0.5 # Original 0.5

        for i in range(num_cols):
            x_offset_source = find_side(i) * x_offset_rs
            x_offset_dest   = 0
            not_first_transfer = False

            if not m300.hw_pipette['has_tip']:
                if TIP_RECYCLING_IN_WASH:
                    pick_up(m300, w3_tip_pos_list[i])
                else:
                    pick_up(m300)
            for transfer_vol in supernatant_transfer_vol:
                #Pickup_height is fixed here
                ctx.comment('Aspirando de la columna del deepwell: ' + str(i+1))
                ctx.comment('La altura de recogida es ' + str(pickup_height) )
                move_vol_multi(m300, reagent = Sample, source = work_destinations[i],
                    dest = waste, vol = transfer_vol, x_offset_source = x_offset_source, x_offset_dest = x_offset_dest,
                    pickup_height = pickup_height, rinse = False, avoid_droplet = False, wait_time = 2, blow_out = False,
                    dispense_bottom_air_gap_before = not_first_transfer, drop_height = waste_drop_height)
                m300.move_to(waste.top(z = waste_drop_height))
                m300.air_gap(Sample.air_gap_vol_bottom)
                not_first_transfer = True

            if recycle_tip == True:
                m300.return_tip()
            else:
                m300.drop_tip(home_after = False)
            if not TIP_RECYCLING_IN_WASH:
                tip_track['counts'][m300] += 8

        log_step_end(start)
        ###############################################################################
        # STEP 15 Desechar sobrenadante
        ########

    ###############################################################################
    # STEP 16 ALLOW DRY
    ########
    STEP += 1
    if STEPS[STEP]['Execute']==True:
        start = log_step_start()

        ctx.comment(' ')
        ctx.delay(seconds=STEPS[STEP]['wait_time'], msg='Dry for ' + format(STEPS[STEP]['wait_time']) + ' segundos.') # 
        ctx.comment(' ')

        log_step_end(start)
        ###############################################################################
        # STEP 16 ALLOW DRY
        ########

    ###############################################################################
    # STEP 17 MAGNET OFF
    ########
    STEP += 1
    if STEPS[STEP]['Execute']==True:
        start = log_step_start()

        # Imán OFF
        magdeck.disengage()

        log_step_end(start)
        ###############################################################################
        # STEP 17 MAGNET OFF
        ########
    
    ###############################################################################
    # STEP 18 Transferir elución
    ########
    STEP += 1
    if STEPS[STEP]['Execute']==True:
        start = log_step_start()

        elution_trips = math.ceil(Elution.reagent_volume / Elution.max_volume_allowed)
        elution_volume = Elution.reagent_volume / elution_trips
        elution_wash_vol = []
        for i in range(elution_trips):
            elution_wash_vol.append(elution_volume + Sample.disposal_volume)
        x_offset_rs = 2.5

        ########
        # Water or elution buffer
        for i in range(num_cols):
            x_offset_source = 0
            x_offset_dest   = -1 * find_side(i) * x_offset_rs # Original 0
            if not m300.hw_pipette['has_tip']:
                pick_up(m300)
                if TIP_RECYCLING_IN_ELUTION:
                    elution_tip_pos_list += [tip_track['tips'][m300][int(tip_track['counts'][m300] / 8)]]
            for transfer_vol in elution_wash_vol:
                #Calculate pickup_height based on remaining volume and shape of container
                [pickup_height, change_col] = calc_height(Elution, multi_well_rack_area, transfer_vol*8)
                ctx.comment('Aspirando desde la columna del reservorio: ' + str(Elution.col))
                ctx.comment('La altura de recogida es ' + str(pickup_height))

                move_vol_multi(m300, reagent = Elution, source = Elution.reagent_reservoir[Elution.col],
                        dest = work_destinations[i], vol = transfer_vol, x_offset_source = x_offset_source, x_offset_dest = x_offset_dest,
                        pickup_height = pickup_height, rinse = False, avoid_droplet = False, wait_time = 0, blow_out = False, drop_height = -35)
            
            if ELUTION_NUM_MIXES > 0:
                ctx.comment(' ')
                ctx.comment('Mezclando muestra with Elution')
                custom_mix(m300, Elution, work_destinations[i], vol = Elution.reagent_volume, rounds = ELUTION_NUM_MIXES,
                    blow_out = False, mix_height = 1, offset = x_offset_dest, drop_height = -35)
            
            m300.move_to(work_destinations[i].top(0))
            m300.air_gap(Elution.air_gap_vol_bottom) #air gap
            
            if recycle_tip == True or TIP_RECYCLING_IN_ELUTION:
                m300.return_tip()
            else:
                m300.drop_tip(home_after = False)
            tip_track['counts'][m300] += 8
            
        log_step_end(start)
        ###############################################################################
        # STEP 18 Transferir elución
        ########

    ###############################################################################
    # STEP 19 Incubación con el imán ON
    ########
    STEP += 1
    if STEPS[STEP]['Execute']==True:
        start = log_step_start()

        # switch on magnet
        magdeck.engage(mag_height)
        ctx.delay(seconds=STEPS[STEP]['wait_time'], msg='Incubación con el imán ON durante ' + format(STEPS[STEP]['wait_time']) + ' segundos.')

        log_step_end(start)
        ####################################################################
        # STEP 19 Incubación con el imán ON
        ########

    ###############################################################################
    # STEP 20 TRANSFER TO FINAL PLATES
    ########
    STEP += 1
    if STEPS[STEP]['Execute']==True:
        start = log_step_start()

        elution_trips = math.ceil(ELUTION_FINAL_VOLUME_PER_SAMPLE / Elution.max_volume_allowed)
        elution_volume = ELUTION_FINAL_VOLUME_PER_SAMPLE / elution_trips
        elution_vol = []
        for i in range(elution_trips):
            elution_vol.append(elution_volume + Elution.disposal_volume)
        x_offset_rs = 2
        for i in range(num_cols):
            x_offset_source = find_side(i) * x_offset_rs
            x_offset_dest   = 0
            if not m300.hw_pipette['has_tip']:
                if TIP_RECYCLING_IN_ELUTION:
                    pick_up(m300, elution_tip_pos_list[i])
                    m300.dispense(Elution.air_gap_vol_top, work_destinations[i].top(z = 0), rate = Elution.flow_rate_dispense)
                else:
                    pick_up(m300)
            for transfer_vol in elution_vol:
                #Pickup_height is fixed here
                pickup_height = 1
                ctx.comment('Aspirando de la columna del deepwell: ' + str(i+1))
                ctx.comment('La altura de recogida es ' + str(pickup_height) )

                move_vol_multi(m300, reagent = Sample, source = work_destinations[i],
                        dest = final_destinations[i], vol = transfer_vol, x_offset_source = x_offset_source, x_offset_dest = x_offset_dest,
                        pickup_height = pickup_height, rinse = False, avoid_droplet = False, wait_time = 0, blow_out = True, touch_tip = False,
                        drop_height = 3)
            
            m300.move_to(final_destinations[i].top(0))
            m300.air_gap(Sample.air_gap_vol_bottom) #air gap

            if recycle_tip == True:
                m300.return_tip()
            else:
                m300.drop_tip(home_after = False)
            if not TIP_RECYCLING_IN_ELUTION:
                tip_track['counts'][m300] += 8

        log_step_end(start)

        ###############################################################################
        # STEP 20 TRANSFER TO FINAL PLATES
        ########

    '''if not ctx.is_simulating():
        with open(file_path,'w') as outfile:
            json.dump(STEPS, outfile)'''

    magdeck.disengage()
    ctx.comment(' ')
    ctx.comment('###############################################')
    ctx.comment('Homing robot')
    ctx.comment('###############################################')
    ctx.comment(' ')
    ctx.home()
###############################################################################
    # Export the time log to a tsv file
    if not ctx.is_simulating():
        with open(file_path, 'w') as f:
            f.write('STEP\texecution\tdescription\twait_time\texecution_time\n')
            for key in STEPS.keys():
                row = str(key)
                for key2 in STEPS[key].keys():
                    row += '\t' + format(STEPS[key][key2])
                f.write(row + '\n')
        f.close()

    ############################################################################
    
    finish_run()
