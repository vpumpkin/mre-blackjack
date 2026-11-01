#include "Core/ManhuntGameMode.h"
#include "Core/ManhuntGameState.h"
#include "Core/ManhuntPlayerState.h"
#include "Core/ManhuntPlayerController.h"
#include "Core/ManhuntCharacter.h"
#include "Core/ManhuntHUD.h"
#include "World/ManhuntBuildingVolume.h"
#include "World/ManhuntExtractionPoint.h"
#include "GameFramework/PlayerStart.h"
#include "Kismet/GameplayStatics.h"
#include "EngineUtils.h"
#include "TimerManager.h"

namespace
{
	FManhuntClassStats MakeStats(float MaxStamina, float Walk, float Sprint, float Drain, float Regen,
		float Parkour, float Grip, float InstantCatch, float Cooldown, float Duration)
	{
		FManhuntClassStats S;
		S.MaxStamina = MaxStamina;
		S.WalkSpeed = Walk;
		S.SprintSpeed = Sprint;
		S.SprintStaminaPerSecond = Drain;
		S.StaminaRegenPerSecond = Regen;
		S.ParkourSpeedMultiplier = Parkour;
		S.GripStrength = Grip;
		S.InstantCatchStaminaRatio = InstantCatch;
		S.AbilityCooldown = Cooldown;
		S.AbilityDuration = Duration;
		return S;
	}
}

AManhuntGameMode::AManhuntGameMode()
{
	GameStateClass = AManhuntGameState::StaticClass();
	PlayerStateClass = AManhuntPlayerState::StaticClass();
	PlayerControllerClass = AManhuntPlayerController::StaticClass();
	DefaultPawnClass = AManhuntCharacter::StaticClass();
	HUDClass = AManhuntHUD::StaticClass();

	BlitzChallengeSeconds = { 180, 390 }; // 3:00 und 6:30

	//                         MaxSt  Walk  Sprint Drain Regen Parkour Grip InstantCatch CD   Dauer
	RunnerStats             = MakeStats(100.f, 320.f, 620.f,  9.f, 7.f, 1.15f, 1.0f, 0.00f,  0.f,  0.f);
	HunterStats.Add(EHunterClass::None,    MakeStats(100.f, 320.f, 600.f, 10.f, 7.f, 1.00f, 1.0f, 0.00f,  0.f,  0.f));
	// Hacker: extrem schlechter Sprinter, verliert sehr schnell Ausdauer.
	HunterStats.Add(EHunterClass::Hacker,  MakeStats( 70.f, 300.f, 520.f, 20.f, 5.f, 1.00f, 1.0f, 0.00f,  0.f,  0.f));
	// Kampfsportler: deutlich mehr Stamina, eisenharter Griff, Sofort-Catch unter 25 % Runner-Stamina.
	HunterStats.Add(EHunterClass::Brawler, MakeStats(160.f, 320.f, 600.f,  9.f, 8.f, 1.00f, 2.5f, 0.25f,  0.f,  0.f));
	// Faehrtenleser: Spuren-Faehigkeit mit festem Cooldown.
	HunterStats.Add(EHunterClass::Tracker, MakeStats(100.f, 320.f, 600.f, 10.f, 7.f, 1.00f, 1.1f, 0.00f, 45.f, 12.f));
}

AManhuntGameState* AManhuntGameMode::GetManhuntGameState() const
{
	return GetGameState<AManhuntGameState>();
}

const FManhuntClassStats& AManhuntGameMode::GetStatsFor(const AManhuntPlayerState* PS) const
{
	if (PS && PS->GetTeam() == EManhuntTeam::Runner)
	{
		return RunnerStats;
	}
	if (const FManhuntClassStats* Found = HunterStats.Find(PS ? PS->GetHunterClass() : EHunterClass::None))
	{
		return *Found;
	}
	if (const FManhuntClassStats* Default = HunterStats.Find(EHunterClass::None))
	{
		return *Default;
	}
	return RunnerStats;
}

// ---------------------------------------------------------------------------
// Spieler & Teams
// ---------------------------------------------------------------------------

void AManhuntGameMode::PostLogin(APlayerController* NewPlayer)
{
	// Team VOR Super zuweisen: Super kann bei laufendem Match sofort spawnen (Pawn-Klasse haengt am Team).
	if (AManhuntPlayerState* PS = NewPlayer ? NewPlayer->GetPlayerState<AManhuntPlayerState>() : nullptr)
	{
		AssignTeam(PS);
		if (PS->GetTeam() == EManhuntTeam::Hunter && IsMatchInProgress())
		{
			PS->SetHunterClass(static_cast<EHunterClass>(FMath::RandRange(1, 3)));
		}
	}
	Super::PostLogin(NewPlayer);
}

void AManhuntGameMode::AssignTeam(AManhuntPlayerState* PS)
{
	int32 Runners = 0;
	int32 Hunters = 0;
	for (APlayerState* Other : GameState->PlayerArray)
	{
		const AManhuntPlayerState* MPS = Cast<AManhuntPlayerState>(Other);
		if (!MPS || MPS == PS)
		{
			continue;
		}
		Runners += MPS->GetTeam() == EManhuntTeam::Runner ? 1 : 0;
		Hunters += MPS->GetTeam() == EManhuntTeam::Hunter ? 1 : 0;
	}

	// Das Team mit dem geringeren Fuellstand bekommt den Spieler (1. Spieler = Runner, 2. = Hunter ...).
	const float RunnerFill = MaxRunners > 0 ? static_cast<float>(Runners) / MaxRunners : 1.f;
	const float HunterFill = MaxHunters > 0 ? static_cast<float>(Hunters) / MaxHunters : 1.f;
	const bool bRunner = Runners < MaxRunners && (RunnerFill <= HunterFill || Hunters >= MaxHunters);

	PS->SetTeam(bRunner ? EManhuntTeam::Runner : EManhuntTeam::Hunter);
	EnsureTaskforceLeader();
}

void AManhuntGameMode::EnsureTaskforceLeader()
{
	AManhuntPlayerState* FirstHunter = nullptr;
	for (APlayerState* Other : GameState->PlayerArray)
	{
		AManhuntPlayerState* MPS = Cast<AManhuntPlayerState>(Other);
		if (!MPS || MPS->GetTeam() != EManhuntTeam::Hunter || MPS->IsPendingKillPending())
		{
			continue;
		}
		if (MPS->IsTaskforceLeader())
		{
			return;
		}
		FirstHunter = FirstHunter ? FirstHunter : MPS;
	}
	if (FirstHunter)
	{
		FirstHunter->SetTaskforceLeader(true);
	}
}

void AManhuntGameMode::Logout(AController* Exiting)
{
	if (AManhuntPlayerState* PS = Exiting ? Exiting->GetPlayerState<AManhuntPlayerState>() : nullptr)
	{
		if (PS->IsTaskforceLeader())
		{
			PS->SetTaskforceLeader(false);
			PS->SetTeam(EManhuntTeam::None);
			EnsureTaskforceLeader();
		}
		if (PS->IsFreeRunner() && IsMatchInProgress())
		{
			PS->SetRunnerStatus(ERunnerStatus::Caught); // Verbindungsabbruch zaehlt als gefangen
			CheckEndConditions();
		}
	}
	Super::Logout(Exiting);
}

UClass* AManhuntGameMode::GetDefaultPawnClassForController_Implementation(AController* InController)
{
	if (const AManhuntPlayerState* PS = InController ? InController->GetPlayerState<AManhuntPlayerState>() : nullptr)
	{
		if (PS->GetTeam() == EManhuntTeam::Runner && RunnerPawnClass)
		{
			return RunnerPawnClass.Get();
		}
		if (PS->GetTeam() == EManhuntTeam::Hunter && HunterPawnClass)
		{
			return HunterPawnClass.Get();
		}
	}
	return Super::GetDefaultPawnClassForController_Implementation(InController);
}

AActor* AManhuntGameMode::ChoosePlayerStart_Implementation(AController* Player)
{
	// PlayerStarts mit Tag "Hunter" (Center Zone) bzw. "Runner" (verteilt auf die Biome).
	const AManhuntPlayerState* PS = Player ? Player->GetPlayerState<AManhuntPlayerState>() : nullptr;
	const FName WantedTag = (PS && PS->GetTeam() == EManhuntTeam::Runner) ? FName(TEXT("Runner")) : FName(TEXT("Hunter"));

	TArray<APlayerStart*> Candidates;
	for (TActorIterator<APlayerStart> It(GetWorld()); It; ++It)
	{
		if (It->PlayerStartTag == WantedTag)
		{
			Candidates.Add(*It);
		}
	}
	if (Candidates.Num() > 0)
	{
		return Candidates[FMath::RandRange(0, Candidates.Num() - 1)];
	}
	return Super::ChoosePlayerStart_Implementation(Player);
}

bool AManhuntGameMode::PlayerCanRestart_Implementation(APlayerController* Player)
{
	const AManhuntPlayerState* PS = Player ? Player->GetPlayerState<AManhuntPlayerState>() : nullptr;
	if (PS && PS->GetTeam() == EManhuntTeam::Runner && PS->GetRunnerStatus() != ERunnerStatus::Free)
	{
		return false; // gefangene/entkommene Runner bleiben Zuschauer
	}
	return Super::PlayerCanRestart_Implementation(Player);
}

bool AManhuntGameMode::TrySelectHunterClass(AManhuntPlayerState* PS, EHunterClass NewClass)
{
	const AManhuntGameState* GS = GetManhuntGameState();
	if (!PS || PS->GetTeam() != EManhuntTeam::Hunter || NewClass == EHunterClass::None)
	{
		return false;
	}
	if (GS && GS->GetPhase() != EManhuntPhase::WaitingForPlayers && GS->GetPhase() != EManhuntPhase::ClassSelection)
	{
		return false; // nur vor Rundenstart
	}
	PS->SetHunterClass(NewClass);
	return true;
}

// ---------------------------------------------------------------------------
// Matchflow
// ---------------------------------------------------------------------------

bool AManhuntGameMode::ReadyToStartMatch_Implementation()
{
	AManhuntGameState* GS = GetManhuntGameState();
	if (!GS)
	{
		return false;
	}
	if (!bClassSelectionStarted)
	{
		if (GetNumPlayers() < MinPlayersToStart)
		{
			return false;
		}
		bClassSelectionStarted = true;
		GS->SetPhase(EManhuntPhase::ClassSelection);
		GS->SetClassSelectionEnd(static_cast<float>(GS->GetServerWorldTimeSeconds()) + ClassSelectionSeconds);
		BroadcastMessage(NSLOCTEXT("Manhunt", "ChooseClass", "Klassenwahl: [1] Hacker  [2] Kampfsportler  [3] Faehrtenleser"), EManhuntTeam::Hunter);
		BroadcastMessage(NSLOCTEXT("Manhunt", "RunnerWait", "Du bist RUNNER. Gleich beginnt die Jagd - 0,00 EUR, nur dein Smartphone."), EManhuntTeam::Runner);
		return false;
	}
	return GS->GetClassSelectionRemaining() <= 0.f;
}

void AManhuntGameMode::HandleMatchHasStarted()
{
	// Hunter ohne Wahl bekommen eine zufaellige Klasse – VOR dem Spawnen (Stats beim Possess).
	for (APlayerState* P : GameState->PlayerArray)
	{
		AManhuntPlayerState* PS = Cast<AManhuntPlayerState>(P);
		if (PS && PS->GetTeam() == EManhuntTeam::Hunter && PS->GetHunterClass() == EHunterClass::None)
		{
			PS->SetHunterClass(static_cast<EHunterClass>(FMath::RandRange(1, 3)));
		}
	}

	Super::HandleMatchHasStarted(); // spawnt alle Spieler

	ElapsedSeconds = 0;
	SpeedhuntsUsed = 0;
	if (AManhuntGameState* GS = GetManhuntGameState())
	{
		GS->SetMatchDuration(MatchDurationSeconds);
		GS->SetElapsedSeconds(0);
		GS->SetSpeedhunt(false, SpeedhuntsPerMatch);
		GS->SetPhase(EManhuntPhase::Hunt);
	}
	GetWorldTimerManager().SetTimer(MatchTickTimer, this, &AManhuntGameMode::MatchTick, 1.f, true);
	BroadcastMessage(NSLOCTEXT("Manhunt", "HuntStart", "DIE JAGD BEGINNT! 10:00 Minuten."));
	OnHuntStarted();
}

void AManhuntGameMode::MatchTick()
{
	AManhuntGameState* GS = GetManhuntGameState();
	if (!GS || bMatchFinished)
	{
		return;
	}
	++ElapsedSeconds;
	GS->SetElapsedSeconds(ElapsedSeconds);

	const bool bFinale = ElapsedSeconds >= FinaleStartSecond;

	// Silent Hunt: jede volle Minute (bis zum Finale)
	if (!bFinale && SilentHuntInterval > 0 && ElapsedSeconds % SilentHuntInterval == 0)
	{
		SendRunnerPings(EManhuntPingType::SilentHunt);
	}

	// Blitz-Challenges
	for (int32 i = 0; i < BlitzChallengeSeconds.Num(); ++i)
	{
		if (BlitzChallengeSeconds[i] == ElapsedSeconds)
		{
			SpawnBlitzDrops(i);
		}
	}

	// Speedhunt: Ziel alle 10 s live pingen
	if (SpeedhuntSecondsLeft > 0)
	{
		--SpeedhuntSecondsLeft;
		AManhuntPlayerState* Target = SpeedhuntTarget.Get();
		if (!Target || !Target->IsFreeRunner())
		{
			SpeedhuntSecondsLeft = 0;
		}
		else if (SpeedhuntSecondsLeft > 0 && SpeedhuntPingInterval > 0 && (SpeedhuntDuration - SpeedhuntSecondsLeft) % SpeedhuntPingInterval == 0)
		{
			SendRunnerPings(EManhuntPingType::Speedhunt, Target);
		}
		if (SpeedhuntSecondsLeft == 0)
		{
			SpeedhuntTarget = nullptr;
			GS->SetSpeedhunt(false, SpeedhuntsPerMatch - SpeedhuntsUsed);
			BroadcastMessage(NSLOCTEXT("Manhunt", "SpeedhuntEnd", "Speedhunt beendet."));
		}
	}

	// Finale 9:00 - 10:00
	if (ElapsedSeconds == FinaleStartSecond)
	{
		StartFinale();
	}
	if (bFinale && FinalePingInterval > 0 && (ElapsedSeconds - FinaleStartSecond) % FinalePingInterval == 0)
	{
		SendRunnerPings(EManhuntPingType::Finale);
	}

	// Zeit abgelaufen
	if (ElapsedSeconds >= MatchDurationSeconds)
	{
		bool bAnyExtracted = false;
		bool bAnyFree = false;
		for (APlayerState* P : GameState->PlayerArray)
		{
			const AManhuntPlayerState* PS = Cast<AManhuntPlayerState>(P);
			if (PS && PS->GetTeam() == EManhuntTeam::Runner)
			{
				bAnyExtracted |= PS->GetRunnerStatus() == ERunnerStatus::Extracted;
				bAnyFree |= PS->GetRunnerStatus() == ERunnerStatus::Free;
			}
		}
		EndManhunt((bAnyExtracted || (!bRunnersMustExtract && bAnyFree)) ? EManhuntTeam::Runner : EManhuntTeam::Hunter);
	}
}

void AManhuntGameMode::SendRunnerPings(EManhuntPingType Type, AManhuntPlayerState* OnlyRunner)
{
	TArray<FManhuntRunnerPing> Pings;

	for (APlayerState* P : GameState->PlayerArray)
	{
		AManhuntPlayerState* PS = Cast<AManhuntPlayerState>(P);
		if (!PS || !PS->IsFreeRunner() || (OnlyRunner && PS != OnlyRunner))
		{
			continue;
		}
		const AManhuntCharacter* Runner = PS->GetPawn<AManhuntCharacter>();
		if (!Runner)
		{
			continue;
		}
		AManhuntPlayerController* RunnerPC = Cast<AManhuntPlayerController>(Runner->GetController());

		// Schwarzmarkt-Ping-Blocker: dieser Ping faellt fuer den Runner komplett aus.
		if (PS->bPingBlockerArmed)
		{
			PS->bPingBlockerArmed = false;
			if (RunnerPC)
			{
				RunnerPC->Client_ShowMessage(NSLOCTEXT("Manhunt", "PingBlocked", "Ping-Blocker hat deinen Ping geschluckt!"));
			}
			continue;
		}

		FManhuntRunnerPing Ping;
		Ping.Runner = PS;
		Ping.Type = Type;

		if (PS->bFakePingArmed)
		{
			PS->bFakePingArmed = false;
			const float Distance = FMath::FRandRange(FakePingOffsetRange.X, FakePingOffsetRange.Y);
			const FVector Fake = Runner->GetActorLocation() + FRotator(0.f, FMath::FRandRange(0.f, 360.f), 0.f).Vector() * Distance;
			Ping.Location = FVector2D(Fake);
			if (RunnerPC)
			{
				RunnerPC->Client_ShowMessage(NSLOCTEXT("Manhunt", "FakeSent", "Fake-Ping gesendet!"));
			}
		}
		else if (const AManhuntBuildingVolume* Building = Runner->GetCurrentBuilding())
		{
			// Nur das Gebaeude im 2D-Grundriss – NIE das Stockwerk.
			Ping.Location = FVector2D(Building->GetActorLocation());
			Ping.BuildingName = Building->BuildingName;
			Ping.BuildingExtent = Building->GetFootprintExtent();
		}
		else
		{
			Ping.Location = FVector2D(Runner->GetActorLocation());
		}
		Pings.Add(Ping);
	}

	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		AManhuntPlayerController* PC = Cast<AManhuntPlayerController>(It->Get());
		const AManhuntPlayerState* PS = PC ? PC->GetPlayerState<AManhuntPlayerState>() : nullptr;
		if (!PS)
		{
			continue;
		}
		if (PS->GetTeam() == EManhuntTeam::Hunter)
		{
			PC->Client_ReceivePings(Pings); // statische Snapshots, nur an Hunter
		}
		else if (PS->IsFreeRunner() && Type != EManhuntPingType::Speedhunt)
		{
			PC->Client_ShowMessage(NSLOCTEXT("Manhunt", "Pinged", "PING! Die Hunter kennen jetzt eure 2D-Position."));
		}
	}
}

bool AManhuntGameMode::TryStartSpeedhunt(AManhuntPlayerState* Requester, AManhuntPlayerState* Target)
{
	AManhuntGameState* GS = GetManhuntGameState();
	if (!GS || !Requester || !Target || bMatchFinished)
	{
		return false;
	}
	if (Requester->GetTeam() != EManhuntTeam::Hunter || !Requester->IsTaskforceLeader() || !Target->IsFreeRunner())
	{
		return false;
	}
	if (SpeedhuntSecondsLeft > 0 || SpeedhuntsUsed >= SpeedhuntsPerMatch)
	{
		return false;
	}
	if (GS->GetPhase() != EManhuntPhase::Hunt && GS->GetPhase() != EManhuntPhase::Finale)
	{
		return false;
	}

	++SpeedhuntsUsed;
	SpeedhuntTarget = Target;
	SpeedhuntSecondsLeft = SpeedhuntDuration;
	GS->SetSpeedhunt(true, SpeedhuntsPerMatch - SpeedhuntsUsed);

	// Alle 3 Runner bekommen den Alarm – aber nicht, wer das Ziel ist.
	BroadcastMessage(NSLOCTEXT("Manhunt", "SpeedhuntRunner", "SPEEDHUNT AKTIV!"), EManhuntTeam::Runner);
	BroadcastMessage(FText::Format(NSLOCTEXT("Manhunt", "SpeedhuntHunter", "Speedhunt auf {0}: Live-Ping alle {1} s"),
		FText::FromString(Target->GetPlayerName()), FText::AsNumber(SpeedhuntPingInterval)), EManhuntTeam::Hunter);
	SendRunnerPings(EManhuntPingType::Speedhunt, Target);
	return true;
}

void AManhuntGameMode::SpawnBlitzDrops(int32 ChallengeIndex)
{
	TArray<AActor*> Spots;
	UGameplayStatics::GetAllActorsWithTag(this, BlitzDropSpawnTag, Spots);

	if (BlitzDropClass && Spots.Num() > 0)
	{
		const int32 Count = FMath::Min(DropsPerChallenge, Spots.Num());
		for (int32 i = 0; i < Count; ++i)
		{
			Spots.Swap(i, FMath::RandRange(i, Spots.Num() - 1));
			FActorSpawnParameters Params;
			Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
			GetWorld()->SpawnActor<AActor>(BlitzDropClass, Spots[i]->GetActorTransform(), Params);
		}
	}
	else
	{
		UE_LOG(LogManhunt, Warning, TEXT("Blitz-Challenge: BlitzDropClass fehlt oder keine Actors mit Tag '%s'."), *BlitzDropSpawnTag.ToString());
	}

	BroadcastMessage(NSLOCTEXT("Manhunt", "Blitz", "BLITZ-CHALLENGE: Risiko-Drops in der Center Zone!"));
	OnBlitzChallenge(ChallengeIndex);
}

void AManhuntGameMode::StartFinale()
{
	if (AManhuntGameState* GS = GetManhuntGameState())
	{
		GS->SetPhase(EManhuntPhase::Finale);
	}

	// In jedem Biom oeffnet sich genau 1 zufaelliger Extraktionspunkt.
	TMap<EManhuntBiome, TArray<AManhuntExtractionPoint*>> ByBiome;
	for (TActorIterator<AManhuntExtractionPoint> It(GetWorld()); It; ++It)
	{
		ByBiome.FindOrAdd(It->Biome).Add(*It);
	}
	for (TPair<EManhuntBiome, TArray<AManhuntExtractionPoint*>>& Pair : ByBiome)
	{
		if (Pair.Value.Num() > 0)
		{
			Pair.Value[FMath::RandRange(0, Pair.Value.Num() - 1)]->SetExtractionActive(true);
		}
	}

	BroadcastMessage(NSLOCTEXT("Manhunt", "Finale", "FINALE! Zonen-Grenzen fallen, Pings alle 15 s, Extraktionspunkte offen!"));
	OnFinaleStarted();
}

// ---------------------------------------------------------------------------
// Fangen, Entkommen, Rundenende
// ---------------------------------------------------------------------------

void AManhuntGameMode::HandleRunnerCaught(AManhuntCharacter* Runner, AManhuntCharacter* Hunter)
{
	AManhuntPlayerState* PS = Runner ? Runner->GetManhuntPlayerState() : nullptr;
	if (!PS || PS->GetRunnerStatus() != ERunnerStatus::Free)
	{
		return;
	}
	PS->SetRunnerStatus(ERunnerStatus::Caught);

	AManhuntPlayerState* HunterPS = Hunter ? Hunter->GetManhuntPlayerState() : nullptr;
	if (HunterPS)
	{
		HunterPS->SetScore(HunterPS->GetScore() + 1.f);
	}
	BroadcastMessage(FText::Format(NSLOCTEXT("Manhunt", "Caught", "{0} wurde von {1} gefangen!"),
		FText::FromString(PS->GetPlayerName()), FText::FromString(HunterPS ? HunterPS->GetPlayerName() : TEXT("?"))));

	RemoveRunnerFromPlay(Runner, 4.f);
	CheckEndConditions();
}

void AManhuntGameMode::HandleRunnerExtracted(AManhuntCharacter* Runner, AActor* ExtractionPoint)
{
	AManhuntPlayerState* PS = Runner ? Runner->GetManhuntPlayerState() : nullptr;
	if (!PS || !PS->IsFreeRunner())
	{
		return;
	}
	PS->SetRunnerStatus(ERunnerStatus::Extracted);
	PS->SetScore(PS->GetScore() + 3.f);
	BroadcastMessage(FText::Format(NSLOCTEXT("Manhunt", "Extracted", "{0} ist ENTKOMMEN!"), FText::FromString(PS->GetPlayerName())));

	RemoveRunnerFromPlay(Runner, 1.f);
	CheckEndConditions();
}

void AManhuntGameMode::RemoveRunnerFromPlay(AManhuntCharacter* Runner, float Delay)
{
	TWeakObjectPtr<AManhuntCharacter> WeakRunner(Runner);
	FTimerHandle Handle;
	GetWorldTimerManager().SetTimer(Handle, FTimerDelegate::CreateWeakLambda(this, [WeakRunner]()
	{
		AManhuntCharacter* R = WeakRunner.Get();
		if (!R)
		{
			return;
		}
		APlayerController* PC = Cast<APlayerController>(R->GetController());
		R->Destroy();
		if (PC)
		{
			PC->ChangeState(NAME_Spectating);
			PC->ClientGotoState(NAME_Spectating);
		}
	}), Delay, false);
}

void AManhuntGameMode::CheckEndConditions()
{
	if (bMatchFinished || !IsMatchInProgress())
	{
		return;
	}
	int32 Total = 0;
	int32 Free = 0;
	int32 Extracted = 0;
	for (APlayerState* P : GameState->PlayerArray)
	{
		const AManhuntPlayerState* PS = Cast<AManhuntPlayerState>(P);
		if (PS && PS->GetTeam() == EManhuntTeam::Runner)
		{
			++Total;
			Free += PS->GetRunnerStatus() == ERunnerStatus::Free ? 1 : 0;
			Extracted += PS->GetRunnerStatus() == ERunnerStatus::Extracted ? 1 : 0;
		}
	}
	if (Total > 0 && Free == 0)
	{
		EndManhunt(Extracted > 0 ? EManhuntTeam::Runner : EManhuntTeam::Hunter);
	}
}

void AManhuntGameMode::EndManhunt(EManhuntTeam Winner)
{
	if (bMatchFinished)
	{
		return;
	}
	bMatchFinished = true;
	GetWorldTimerManager().ClearTimer(MatchTickTimer);

	if (AManhuntGameState* GS = GetManhuntGameState())
	{
		GS->SetWinningTeam(Winner);
		GS->SetSpeedhunt(false, 0);
		GS->SetPhase(EManhuntPhase::Ended);
	}
	BroadcastMessage(Winner == EManhuntTeam::Runner
		? NSLOCTEXT("Manhunt", "RunnersWin", "DIE RUNNER GEWINNEN!")
		: NSLOCTEXT("Manhunt", "HuntersWin", "DIE HUNTER GEWINNEN!"));
	OnManhuntEnded(Winner);
	EndMatch();

	if (RestartDelayAfterMatch > 0.f)
	{
		FTimerHandle Handle;
		GetWorldTimerManager().SetTimer(Handle, FTimerDelegate::CreateWeakLambda(this, [this]() { RestartGame(); }), RestartDelayAfterMatch, false);
	}
}

void AManhuntGameMode::BroadcastMessage(const FText& Message, EManhuntTeam OnlyTeam)
{
	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		AManhuntPlayerController* PC = Cast<AManhuntPlayerController>(It->Get());
		if (!PC)
		{
			continue;
		}
		const AManhuntPlayerState* PS = PC->GetPlayerState<AManhuntPlayerState>();
		if (OnlyTeam == EManhuntTeam::None || (PS && PS->GetTeam() == OnlyTeam))
		{
			PC->Client_ShowMessage(Message);
		}
	}
}
